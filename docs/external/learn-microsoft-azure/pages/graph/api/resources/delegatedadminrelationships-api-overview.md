# Granular delegated admin privileges (GDAP) API overview

Namespace: microsoft.graph

As part of the Microsoft Partner Center ecosystem, Microsoft partners in the Cloud Solution Provider, Value Added Reseller, or Advisor programs can perform administrative operations on their customer tenants to help manage the customer's services, for example, Microsoft Entra and Microsoft 365. This capability previously allowed partners to assume a Global Administrator role in the customer tenant indefinitely, creating potential security exposures and limiting market potential.

**Granular delegated admin privileges (GDAP)** provide partners with least-privileged access to their customer tenants following the [Zero Trust cybersecurity model](https://learn.microsoft.com/en-us/security/zero-trust/). Through GDAP, partners configure and request granular and time-bound access to their customers' environments, and customers must explicitly grant this least-privileged access to partners. In addition, partners must request specific roles for customer tenant administration for a definite amount of time. This control eliminates the need for partners to have the Global Administrator role in their customer's tenant but rather, they now have lesser privileged permissions that they absolutely need for delegated administrative tasks.

For more information about GDAP, see:

- [Introduction to granular delegated admin privileges (GDAP)](https://learn.microsoft.com/en-us/partner-center/gdap-introduction)
- [Least-privileged roles by task](https://learn.microsoft.com/en-us/partner-center/gdap-least-privileged-roles-by-task)

## GDAP workflow

### Lifecycle of a GDAP relationship

The following diagram shows the status of the Delegated Admin relationship transitions.

![Delegated Admin relationship status transition diagram](https://learn.microsoft.com/en-us/graph/v1.0/images/relationship-status-transitions.png?view=graph-rest-1.0)

1. [Create delegatedAdminRelationship](https://learn.microsoft.com/en-us/graph/api/tenantrelationship-post-delegatedadminrelationships?view=graph-rest-1.0)
2. [Update delegatedAdminRelationship](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-update?view=graph-rest-1.0)
3. [Create delegatedAdminRelationshipRequest](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-requests?view=graph-rest-1.0) (action: lockForApproval)
4. [Create delegatedAdminRelationshipRequest](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-requests?view=graph-rest-1.0) (action: terminate)

> After running the [Create delegatedAdminRelationshipRequest](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-requests?view=graph-rest-1.0) API with the `lockForApproval` action, build the customer invitation link by using the following URI template, where _{adminRelationshipID}_ is the ID of admin relationship request.
>
> `https://admin.microsoft.com/AdminPortal/Home#/partners/invitation/granularAdminRelationships/{adminRelationshipID}`

Send the invitation link to the customer for them to approve the GDAP request. For example, `https://admin.microsoft.com/AdminPortal/Home#/partners/invitation/granularAdminRelationships/5d027261-d21f-4aa9-b7db-7fa1f56fb163-8777b240-c6f0-4469-9e98-a3205431b836` is an invitation link, where `5d027261-d21f-4aa9-b7db-7fa1f56fb163-8777b240-c6f0-4469-9e98-a3205431b836` is the admin relationship request ID. After the customer approves the GDAP request, the GDAP relationship will transition to an active state.

To finalize the workflow for enabling admin on behalf of (AOBO) management of the customer's tenant, proceed by creating a new access assignment for the delegated admin relationship by using the [Create accessAssignments](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-accessassignments?view=graph-rest-1.0) API.

### Lifecycle of a GDAP relationship access assignment

The delegated admin access assignment goes through the status transitions shown in the following diagram.

![Delegated admin access assignment status transition diagram](https://learn.microsoft.com/en-us/graph/v1.0/images/access-assignment-status-transitions.png?view=graph-rest-1.0)

1. [Create delegatedAdminAccessAssignment](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-accessassignments?view=graph-rest-1.0)
2. [Delete delegatedAdminAccessAssignment](https://learn.microsoft.com/en-us/graph/api/delegatedadminaccessassignment-delete?view=graph-rest-1.0)

## Use cases for GDAP APIs

This section describes the ways that Microsoft partners can use the GDAP APIs to programmatically manage delegated admin relationships for their customers.

### Delegated admin relationship

| Use cases | APIs |
| --- | --- |
| Create a new delegated admin relationship for approval by any customer <br> Create a new delegated admin relationship for approval by a specific customer | [Create delegatedAdminRelationship](https://learn.microsoft.com/en-us/graph/api/tenantrelationship-post-delegatedadminrelationships?view=graph-rest-1.0) |
| List all delegated admin relationships of a partner <br> List all delegated admin relationships for a specific customer | [List delegatedAdminRelationships](https://learn.microsoft.com/en-us/graph/api/tenantrelationship-list-delegatedadminrelationships?view=graph-rest-1.0) |
| Get a delegated admin relationship by ID | [Get delegatedAdminRelationship](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-get?view=graph-rest-1.0) |
| Delete delegated admin relationship | [Delete delegatedAdminRelationship](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-delete?view=graph-rest-1.0) |

### Delegated admin relationship request

| Use cases | APIs |
| --- | --- |
| Create a delegated admin relationship request to lock a relationship for customer approval or terminate an existing relationship. | [Create requests](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-requests?view=graph-rest-1.0) |
| Get a delegated admin relationship request by ID | [Get delegatedAdminRelationshipRequest](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationshiprequest-get?view=graph-rest-1.0) |
| List all delegated admin relationship requests for a given relationship | [List requests](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-list-requests?view=graph-rest-1.0) |

### Role assignments

| Use cases | APIs |
| --- | --- |
| Create new delegated admin access assignment for a delegated admin relationship | [Create accessAssignments](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-post-accessassignments?view=graph-rest-1.0) |
| List access assignments for a delegated admin relationship | [List accessAssignments](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-list-accessassignments?view=graph-rest-1.0) |
| Get a delegated admin relationship access assignment by ID | [Get delegatedAdminAccessAssignment](https://learn.microsoft.com/en-us/graph/api/delegatedadminaccessassignment-get?view=graph-rest-1.0) |
| Delete an access assignment of a delegated admin relationship | [Delete delegatedAdminAccessAssignment](https://learn.microsoft.com/en-us/graph/api/delegatedadminaccessassignment-delete?view=graph-rest-1.0) |
| Update role assignments for a delegated admin relationship access assignment | [Update delegatedAdminAccessAssignment](https://learn.microsoft.com/en-us/graph/api/delegatedadminaccessassignment-update?view=graph-rest-1.0) |

### Long-running operations

| Use cases | APIs |
| --- | --- |
| List all long running operations of a delegated admin relationship | [List operations](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationship-list-operations?view=graph-rest-1.0) |
| Get a long running operation of a delegated admin relationship | [Get delegatedAdminRelationshipOperation](https://learn.microsoft.com/en-us/graph/api/delegatedadminrelationshipoperation-get?view=graph-rest-1.0) |

### Delegated admin customers

| Use cases | APIs |
| --- | --- |
| List all delegated admin customers | [List delegatedAdminCustomers](https://learn.microsoft.com/en-us/graph/api/tenantrelationship-list-delegatedadmincustomers?view=graph-rest-1.0) |
| Get a single delegated admin customer by ID | [Get delegatedAdminCustomer](https://learn.microsoft.com/en-us/graph/api/delegatedadmincustomer-get?view=graph-rest-1.0) |
| Get service management details for a delegated admin customer | [List serviceManagementDetails](https://learn.microsoft.com/en-us/graph/api/delegatedadmincustomer-list-servicemanagementdetails?view=graph-rest-1.0) |

## Permissions

To manage delegated admin relationships, the calling principal must be in the partner tenant and be granted the appropriate [granular delegated admin privileges permissions](https://learn.microsoft.com/en-us/graph/permissions-reference#granular-delegated-admin-privileges-gdap-permissions).

## Zero Trust

This feature helps organizations to align their tenants with the three guiding principles of a Zero Trust architecture:

- Verify explicitly
- Use least privilege
- Assume breach

To find out more about Zero Trust and other ways to align your organization to the guiding principles, see the [Zero Trust Guidance Center](https://learn.microsoft.com/en-us/security/zero-trust/).

## Related content

- [Introduction to granular delegated admin privileges (GDAP)](https://learn.microsoft.com/en-us/partner-center/gdap-introduction)

* * *
