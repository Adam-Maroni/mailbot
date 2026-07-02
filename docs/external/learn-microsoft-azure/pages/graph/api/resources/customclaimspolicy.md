# customClaimsPolicy resource type

Namespace: microsoft.graph

Important

APIs under the `/beta` version in Microsoft Graph are subject to change. Use of these APIs in production applications is not supported. To determine whether an API is available in v1.0, use the **Version** selector.

Represents a claims policy that allows application admins to customize the claims emitted in tokens affected by this policy. Learn more about this policy in the following articles:

- [Customize claims using the custom claims policy (preview)](https://learn.microsoft.com/en-us/entra/identity-platform/claims-customization-custom-claims-policy)
- [Claims customization using a policy](https://learn.microsoft.com/en-us/entra/identity-platform/reference-claims-customization) to learn the difference between this policy and the [claims mapping policy](https://learn.microsoft.com/en-us/graph/api/resources/claimsmappingpolicy?view=graph-rest-beta)

Inherits from [entity](https://learn.microsoft.com/en-us/graph/api/resources/entity?view=graph-rest-beta).

## Methods

| Method | Return type | Description |
| --- | --- | --- |
| [Get](https://learn.microsoft.com/en-us/graph/api/customclaimspolicy-get?view=graph-rest-beta) | [customClaimsPolicy](https://learn.microsoft.com/en-us/graph/api/resources/customclaimspolicy?view=graph-rest-beta) | Read the properties and relationships of a custom claims policy object. |
| [Create or replace](https://learn.microsoft.com/en-us/graph/api/serviceprincipal-put-claimspolicy?view=graph-rest-beta) | [customClaimsPolicy](https://learn.microsoft.com/en-us/graph/api/resources/customclaimspolicy?view=graph-rest-beta) | Create a new custom claims policy object if it doesn't exist, or replace an existing one. |
| [Update](https://learn.microsoft.com/en-us/graph/api/customclaimspolicy-update?view=graph-rest-beta) | [customClaimsPolicy](https://learn.microsoft.com/en-us/graph/api/resources/customclaimspolicy?view=graph-rest-beta) | Update the properties of a custom claims policy object. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| audienceOverride | String | If specified, it overrides the content of the audience claim for WS-Federation and SAML2 protocols. A custom signing key must be used for audienceOverride to be applied, otherwise, the audienceOverride value is ignored. The value provided must be in the format of an absolute URI. |
| claims | [customClaim](https://learn.microsoft.com/en-us/graph/api/resources/customclaim?view=graph-rest-beta) collection | Defines which claims are present in the tokens affected by the policy, in addition to the basic claim and the core claim set. Inherited from [customclaimbase](https://learn.microsoft.com/en-us/graph/api/resources/customclaimbase?view=graph-rest-beta). |
| id | String | Policy identifier string. Inherited from [entity](https://learn.microsoft.com/en-us/graph/api/resources/entity?view=graph-rest-beta). |
| includeApplicationIdInIssuer | Boolean | Indicates whether the application ID is added to the claim. It is relevant only for SAML2.0 and if a custom signing key is used. the default value is `true`. Optional. |
| includeBasicClaimSet | Boolean | Determines whether the basic claim set is included in tokens affected by this policy. If set to `true`, all claims in the basic claim set are emitted in tokens affected by the policy. By default the basic claim set isn't in the tokens unless they're explicitly configured in this policy. |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.customClaimsPolicy",
  "id": "String (identifier)",
  "includeBasicClaimSet": "Boolean",
  "includeApplicationIdInIssuer": "Boolean",
  "audienceOverride": "String",
  "groupFilter": {
    "@odata.type": "microsoft.graph.groupClaimFilterBase"
  },
  "claims": [\
    {\
      "@odata.type": "microsoft.graph.customClaim"\
    }\
  ]
}
```

* * *
