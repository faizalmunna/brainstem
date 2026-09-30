---
name: ecs-task-role-vs-execution-role-permission-confusion
description: An ECS task fails to pull a private image or fetch a secret, or the running application cannot call AWS APIs, because permissions were granted to the wrong of the two distinct IAM roles.
triggers: ["ecs task cannot access secrets manager", "ecs unable to pull image from ecr access denied", "ecs task role vs execution role", "fargate task cannot call aws api", "ecs container cannot assume permissions"]
permissions: ["READ"]
---

## Symptom
An ECS task either fails to even start -- stuck pulling its container
image from ECR, or failing to resolve a secret/parameter referenced in
the task definition, with the failure visible only in the stopped task's
`stoppedReason` rather than application logs -- or it starts fine but the
*application code running inside the container* gets `AccessDenied` when
calling an AWS API (e.g., reading from S3, writing to DynamoDB), despite
someone being confident "the IAM role has the right permissions."

## Likely causes
1. **Permissions needed to start the task were granted to the task role
   instead of the execution role, or vice versa** -- ECS has two
   distinct IAM roles with non-overlapping responsibilities: the
   **execution role** is used by the ECS agent itself to pull the
   container image (including from a private ECR repo), fetch secrets/
   SSM parameters referenced in the task definition, and write to
   CloudWatch Logs; the **task role** is assumed by the application code
   running inside the container for its own AWS API calls. Granting
   ECR/Secrets Manager permissions to the task role (instead of the
   execution role) looks reasonable but does nothing for image pulls or
   secret injection, because those happen before the task role is ever
   in play.
2. **No task role is attached at all**, and application code inside the
   container is relying on the execution role's permissions by mistaken
   assumption -- the execution role is never available to application
   code at runtime, so any AWS SDK call from inside the container with no
   task role attached has no credentials at all (falling through to
   whatever the underlying EC2 instance profile provides, if EC2 launch
   type, which is usually not intended).
3. **The task definition references a secret (`secrets` block, pulling
   from Secrets Manager/SSM) but the execution role's policy doesn't
   include the necessary `secretsmanager:GetSecretValue` /
   `ssm:GetParameters` and, for a customer-managed KMS key, the
   corresponding `kms:Decrypt`** -- task startup fails specifically at
   the secret-resolution step, distinguishable from an image-pull
   failure by the `stoppedReason` text.
4. **The execution role's ECR permissions are scoped to the wrong
   repository/registry** (e.g., overly narrow resource ARN restricting
   to one repo when the image is in another, or missing
   `ecr:GetAuthorizationToken`, which -- unlike the other ECR actions --
   must be granted on all resources, `"Resource": "*"`, since it isn't
   repo-scoped).
5. **Task role permissions are correct in the task definition, but the
   running task is using an older task definition revision that was
   registered before the task role was added/updated**, because updating
   a task role requires a new task definition revision and a service
   redeployment -- editing IAM alone doesn't retroactively affect
   already-running tasks or a service still targeting the old revision.

## Diagnose
- For a task that fails to start, check `stoppedReason` on the stopped
  task (`aws ecs describe-tasks`) -- it typically names specifically
  whether the failure was an image pull (`CannotPullContainerError`) or
  a resource resolution failure (referencing the specific secret/
  parameter ARN), which tells you immediately whether the execution role
  is the one to check.
- Identify which role is attached where: `taskRoleArn` vs.
  `executionRoleArn` in the task definition (`aws ecs describe-task-
  definition`) -- confirm both are set (a missing `taskRoleArn` combined
  with in-container AWS calls failing is diagnostic on its own).
- For application-level `AccessDenied` errors from inside the running
  container, confirm which role's credentials the SDK is actually using
  by checking the container's metadata endpoint
  (`curl http://169.254.170.2$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`
  from inside the task, if debugging access is available) -- this
  returns the task role's actual current permissions context, removing
  ambiguity about which role is in effect.
- Check the execution role's attached policy for the specific actions
  needed at startup (`ecr:GetAuthorizationToken`, `ecr:BatchGetImage`,
  `ecr:GetDownloadUrlForLayer`, `secretsmanager:GetSecretValue`,
  `logs:CreateLogStream`/`PutLogEvents`) versus what's actually attached,
  rather than assuming "it has AdministratorAccess so it must be fine" --
  check the *actual* attached policy document.
- Confirm the running service's task definition revision number matches
  the one where the relevant role was last updated (`aws ecs describe-
  services` shows the active `taskDefinition` ARN including revision).

## Fix
Grant image-pull, secret-resolution, and logging permissions to the
**execution role** exclusively, and grant applicationlevel AWS API
permissions the code itself needs to the **task role** exclusively --
keep these two policies conceptually and practically separate rather
than consolidating them onto one role "for simplicity," since that
conflation is exactly what causes this confusion repeatedly. Always
attach a distinct, minimally-scoped task role for any task whose code
calls AWS APIs, rather than omitting it or relying on incidental
permissions from the execution role or an EC2 instance profile. Include
`ecr:GetAuthorizationToken` with `Resource: "*"` on the execution role
specifically (it cannot be scoped to a repository ARN), alongside
repo-scoped `ecr:BatchGetImage`/`GetDownloadUrlForLayer` for the specific
repositories the task pulls from. After any task role or execution role
policy change tied to a task definition, register a new task definition
revision and update the service to use it, rather than assuming an IAM
policy edit alone takes effect on already-running or already-scheduled
tasks.

## Pitfalls
Attaching every needed permission to both roles "to be safe" muddies the
security boundary between what the ECS control plane can do versus what
application code can do, and makes future audits harder -- if application
code is ever compromised, an overly broad task role that also carries
execution-role-style permissions (or vice versa) expands the blast
radius unnecessarily. Also, granting `AdministratorAccess` or overly
broad wildcard permissions to "make the access denied go away" without
identifying which specific action failed hides exactly which permission
was actually missing, making the next similar issue harder to diagnose
quickly.

## Verify
Force a new deployment of the service and confirm the task reaches
`RUNNING` state without a `stoppedReason` related to image pull or
secret resolution. From inside the running container (via `ecs exec` or
application logs), confirm the specific AWS API call the application
needs to make succeeds, and cross-check via CloudTrail that the API call
was made using the expected task role's assumed-role session, not an
unexpected identity.
