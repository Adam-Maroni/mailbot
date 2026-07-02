# subscribedSku resource type

Namespace: microsoft.graph

Represents information about a service SKU that a company is subscribed to. Use the values of **skuId** and **servicePlans** \> **servicePlanId** to assign licenses to unassigned users and groups through the [user: assignLicense](https://learn.microsoft.com/en-us/graph/api/user-assignlicense?view=graph-rest-1.0) and [group: assignLicense](https://learn.microsoft.com/en-us/graph/api/group-assignlicense?view=graph-rest-1.0) APIs respectively.

For more information about subscriptions and licenses, see [Subscriptions, licenses, accounts, and tenants for Microsoft's cloud offerings](https://learn.microsoft.com/en-us/microsoft-365/enterprise/subscriptions-licenses-accounts-and-tenants-for-microsoft-cloud-offerings).

Inherits from [directoryObject](https://learn.microsoft.com/en-us/graph/api/resources/directoryobject?view=graph-rest-1.0).

## Methods

| Method | Return Type | Description |
| --- | --- | --- |
| [Get](https://learn.microsoft.com/en-us/graph/api/subscribedsku-get?view=graph-rest-1.0) | [subscribedSku](https://learn.microsoft.com/en-us/graph/api/resources/subscribedsku?view=graph-rest-1.0) | Get a specific commercial subscription that an organization has acquired. |
| [List](https://learn.microsoft.com/en-us/graph/api/subscribedsku-list?view=graph-rest-1.0) | [subscribedSku](https://learn.microsoft.com/en-us/graph/api/resources/subscribedsku?view=graph-rest-1.0) collection | Get the list of commercial subscriptions that an organization has acquired. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| accountId | String | The unique ID of the account this SKU belongs to. |
| accountName | String | The name of the account this SKU belongs to. |
| appliesTo | String | The target class for this SKU. Only SKUs with target class `User` are assignable. The possible values are: `User`, `Company`. |
| capabilityStatus | String | `Enabled` indicates that the **prepaidUnits** property has at least one unit that is enabled. `LockedOut` indicates that the customer canceled their subscription. The possible values are: `Enabled`, `Warning`, `Suspended`, `Deleted`, `LockedOut`. |
| consumedUnits | Int32 | The number of licenses that have been assigned. |
| id | String | The unique identifier for the subscribed sku object. Key, not nullable. |
| prepaidUnits | [licenseUnitsDetail](https://learn.microsoft.com/en-us/graph/api/resources/licenseunitsdetail?view=graph-rest-1.0) | Information about the number and status of prepaid licenses. |
| servicePlans | [servicePlanInfo](https://learn.microsoft.com/en-us/graph/api/resources/serviceplaninfo?view=graph-rest-1.0) collection | Information about the service plans that are available with the SKU. Not nullable. |
| skuId | Guid | The unique identifier (GUID) for the service SKU. |
| skuPartNumber | String | The SKU part number; for example: `AAD_PREMIUM` or `RMSBASIC`. To get a list of commercial subscriptions that an organization has acquired, see [List subscribedSkus](https://learn.microsoft.com/en-us/graph/api/subscribedsku-list?view=graph-rest-1.0). |
| subscriptionIds | String collection | A list of all subscription IDs associated with this SKU. |

## Relationships

None

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "accountId": "String",
  "accountName": "String",
  "appliesTo": "String",
  "capabilityStatus": "String",
  "consumedUnits": "Int32",
  "id": "String (identifier)",
  "prepaidUnits": { "@odata.type": "microsoft.graph.licenseUnitsDetail" },
  "servicePlans": [{ "@odata.type": "microsoft.graph.servicePlanInfo" }],
  "skuId": "String",
  "skuPartNumber": "String",
  "subscriptionIds": ["String"]
}
```

## Related content

- [Product names and service plan identifiers for licensing](https://learn.microsoft.com/en-us/azure/active-directory/enterprise-users/licensing-service-plan-reference)

* * *
