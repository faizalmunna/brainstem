---
name: vnet-peering-partial-connectivity-route-nsg-scoping
description: VNet peering or ExpressRoute connectivity works for one subnet but fails for another subnet in the same peered virtual network.
triggers: ["vnet peering works for one subnet not another", "expressroute connectivity partial subnet", "peered vnet some subnets unreachable", "route table missing on subnet blocks traffic"]
permissions: ["READ"]
---

## Symptom
Two VNets are peered (or connected via ExpressRoute back to on-prem), and
resources in one subnet can reach resources across the peering/circuit
just fine, but resources in a different subnet within the *same* VNet
cannot -- despite VNet peering itself showing "Connected" status and no
account-wide outage. It looks like the peering is broken, but it's scoped
per-subnet, not per-VNet.

## Likely causes
1. **A Network Security Group (NSG) attached to the failing subnet (or to
   the specific NICs in it) has rules that block the peered/remote address
   range**, while the working subnet either has no NSG or a more
   permissive one -- NSGs are applied per subnet/NIC, not per VNet, so
   peering being "connected" says nothing about whether an NSG two layers
   down actually allows the traffic.
2. **A User Defined Route (UDR) on the failing subnet's route table
   redirects traffic destined for the peered range through a network
   virtual appliance/firewall that either isn't configured to allow it or
   isn't running**, while the working subnet has no route table (using
   default system routes, which include the peering route directly) or a
   different, correctly configured one -- route tables are also a
   per-subnet association, so subnets in the same VNet can have entirely
   different effective routes.
3. **VNet peering's "Allow forwarded traffic" or "Use remote gateways"
   settings are scoped in a way that blocks specific traffic shapes** --
   e.g., traffic from an NVA-routed subnet counts as "forwarded" and is
   silently dropped if the peering doesn't have that setting enabled,
   while directly-originated traffic from a different subnet passes
   because it was never forwarded in the first place.
4. **The failing subnet is associated with a different NSG/route table
   inherited from a different deployment (e.g., created via a different
   Terraform module or manual process) that was never updated when
   peering or ExpressRoute connectivity was set up**, a configuration-drift
   problem rather than a peering problem per se.
5. **For ExpressRoute specifically, route propagation (BGP) to the
   failing subnet's route table is disabled** (`Disable BGP route
   propagation` set on that subnet's UDR) while other subnets either have
   no UDR or have it enabled, so the on-prem routes exist on the circuit
   but never populate into that specific subnet's effective routes.

## Diagnose
- Use Azure Network Watcher's **Effective Routes** view (per NIC or via
  `az network nic show-effective-route-table`) on a VM/resource in the
  failing subnet and compare it against the same view for a working
  subnet -- differences in the destination range's next hop (or its
  absence entirely) pinpoint whether it's a routing problem immediately.
- Use Network Watcher's **Effective Security Rules** (per NIC) on the
  failing subnet's resource and check specifically for a deny rule
  matching the peered/remote CIDR, comparing against the working subnet's
  effective rules.
- Run Network Watcher's **IP Flow Verify** or **Connection Troubleshoot**
  from a resource in the failing subnet to the specific remote destination
  and port, which reports the exact rule (NSG or route) responsible for a
  block rather than requiring manual correlation.
- Check each subnet's Route Table association
  (`az network vnet subnet show --query routeTable`) and NSG association
  (`--query networkSecurityGroup`) side by side for the working and
  failing subnet to confirm they actually differ, rather than assuming
  they're the same because they're in the same VNet.
- For ExpressRoute, check the route table associated with the failing
  subnet for `Disable BGP route propagation` and compare its effective
  routes against a subnet where on-prem routes are visibly present.

## Fix
Treat subnet-level NSG and route table associations as the actual unit of
network policy in Azure, not the VNet -- audit every subnet's NSG and UDR
individually when diagnosing "partial" connectivity rather than assuming
uniform behavior across a peered or ExpressRoute-connected VNet. Correct
the specific missing allow rule (NSG) or missing/incorrect next hop (UDR)
on the failing subnet to match the intended connectivity design, and if
subnets are meant to share policy, associate them with the same NSG/route
table (or manage both via a shared Terraform/Bicep module) rather than
maintaining parallel configurations that can drift. For ExpressRoute-
specific gaps, enable BGP route propagation on affected subnets unless
there's a deliberate reason a specific subnet should not receive on-prem
routes (e.g., it's meant to remain isolated), and document that
exception explicitly if so.

## Pitfalls
Removing a subnet's NSG entirely to "match" a working subnet that has none
can eliminate an intentional security boundary for whatever resources are
actually in that subnet -- diagnose which specific rule is blocking
traffic and add a scoped allow rule instead of deleting protection
wholesale. Similarly, disabling BGP route propagation was sometimes a
deliberate isolation choice (e.g., for a subnet hosting a firewall
appliance that needs static routing); re-enabling it without checking why
it was disabled can create asymmetric routing or bypass an intended
inspection point.

## Verify
Re-run Network Watcher's Effective Routes and Effective Security Rules on
the previously-failing subnet's resource and confirm the peered/on-prem
CIDR now appears with the expected next hop and no blocking deny rule
precedes the needed allow rule. Perform an actual connectivity test
(TCP ping via `Test-NetConnection`, or the application-level request that
originally failed) from a resource in the fixed subnet to the remote
target and confirm success. Re-check the previously-working subnet with
the same tools to confirm the fix didn't inadvertently change its
behavior.
