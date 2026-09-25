---
name: vpc-nacl-silently-blocking-traffic
description: Traffic is silently dropped between VPC resources despite correctly configured security group rules because a subnet-level network ACL is blocking it.
triggers: ["security groups look correct but connection still fails", "vpc traffic blocked no security group issue", "network acl blocking traffic", "ec2 connection timeout correct security group", "nacl ephemeral port blocking return traffic"]
permissions: ["READ"]
---

## Symptom
A connection between two resources in a VPC (EC2-to-RDS, ALB-to-target,
cross-subnet traffic) times out or is refused, even after careful review
confirms the security groups on both sides allow the traffic in both
directions -- the failure persists regardless of how many times the
security group rules are re-verified, because the actual blocking layer
is one level up, at the subnet's Network ACL.

## Likely causes
1. **A NACL rule explicitly denies the traffic**, and because NACLs are
   evaluated by rule number in ascending order with first-match-wins, a
   low-numbered `DENY` rule can block traffic that a higher-numbered
   `ALLOW` rule further down would otherwise have permitted -- unlike
   security groups, NACL rule order matters.
2. **NACLs are stateless, unlike security groups** -- an outbound
   request's *return traffic* must be explicitly allowed by an inbound
   NACL rule (typically on the ephemeral port range, 1024-65535), and a
   NACL that only allows the "obvious" direction (e.g., inbound 443) but
   not the ephemeral-port return path silently drops responses even
   though the initial request went out fine.
3. **The default NACL was replaced with a custom one that's missing a
   rule** for a specific subnet or a specific type of traffic (e.g.,
   allowing HTTP/HTTPS but forgetting the database port, or forgetting
   ICMP needed for path MTU discovery), which wasn't a problem under the
   permissive default NACL but breaks once a more restrictive custom
   NACL is applied.
4. **The NACL applies to the correct subnet, but the resource being
   diagnosed is actually in a different subnet than assumed** (e.g., an
   ALB or RDS instance has ENIs/nodes spread across multiple subnets,
   and only some of those subnets have the restrictive NACL), so testing
   against one instance/AZ shows the problem while another appears fine,
   confusing the diagnosis.
5. **A recently changed NACL rule (via Terraform/CloudFormation drift
   or a manual console change) introduced an unintended deny**, often
   from a rule number collision or an overly broad CIDR-based deny meant
   for a different purpose that inadvertently matches this traffic too.

## Diagnose
- Identify the exact subnet(s) both the source and destination resources
  sit in (`aws ec2 describe-network-interfaces` or the resource's own
  subnet ID), then find the NACL associated with each subnet (`aws ec2
  describe-network-acls --filters Name=association.subnet-id,Values=<id>`)
  -- don't assume both ends share the same NACL.
- Read the NACL's rules **in rule-number order** for both inbound and
  outbound, specifically checking for a `DENY` with a lower rule number
  than the relevant `ALLOW`, and specifically checking that inbound rules
  include the ephemeral port range (1024-65535, or 32768-65535 depending
  on OS) for return traffic on any outbound-initiated connection.
- Use **VPC Flow Logs** filtered to the specific source/destination
  IP and port, and look at the `action` field (`ACCEPT`/`REJECT`) --
  flow logs will show a `REJECT` at the exact point of failure and
  distinguish NACL-level rejection from security-group-level rejection
  from an application-level refusal.
- Use the **VPC Reachability Analyzer** to test the specific path between
  the two ENIs -- it explicitly traces through security groups and NACLs
  and names which one is the actual blocker if any.
- Compare the current NACL rule set against source-controlled
  infrastructure-as-code (Terraform state, CloudFormation template) to
  check for drift if the NACL was expected to allow this traffic.

## Fix
Add the specific missing `ALLOW` rule to the NACL at a rule number that
takes effect before any conflicting `DENY` (remembering NACL evaluation
is first-match, ascending order, so insert with enough headroom in the
numbering scheme for future rules). Because NACLs are stateless, always
add both directions explicitly: the request direction (e.g., inbound 443
from the source CIDR) and the ephemeral-port return direction (outbound
1024-65535 to the source CIDR, or vice versa depending on which side
initiates). Where fine-grained NACL rules aren't providing meaningful
additional security over already-correct security groups (which are
stateful and resource-scoped, generally the more precise control),
consider reverting to the default allow-all NACL and relying on security
groups as the primary control, reserving custom NACLs for subnet-wide
policies that genuinely need to apply regardless of instance-level
security group configuration (e.g., blocking a known-bad CIDR range at
the subnet boundary).

## Pitfalls
Fixing this by making the NACL fully permissive (allow all, both
directions) "to stop worrying about it" removes a defense-in-depth layer
that may have been intentionally restrictive for compliance or blast-
radius reasons -- if a custom NACL exists, find out why before making it
a no-op. Also, remembering only the request direction and forgetting the
ephemeral-port return rule is the single most common half-fix: it makes
outbound-initiated connections still fail even after "fixing" the NACL,
because the response can't get back in.

## Verify
Re-run VPC Reachability Analyzer for the same path and confirm it now
reports the path as reachable with no blocking component. Then perform
the actual application-level connection (not just a port-level check)
and confirm it succeeds, and check VPC Flow Logs for the same
source/destination/port show `ACCEPT` for both the outbound request and
inbound return traffic.
