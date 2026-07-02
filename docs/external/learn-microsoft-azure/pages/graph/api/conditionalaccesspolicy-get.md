# Get conditionalAccessPolicy

Namespace: microsoft.graph

Retrieve the properties and relationships of a [conditionalAccessPolicy](https://learn.microsoft.com/en-us/graph/api/resources/conditionalaccesspolicy?view=graph-rest-1.0) object.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Policy.Read.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | Policy.Read.All | Not available. |

Important

For delegated access using work or school accounts where the signed-in user is acting on another user, they must be assigned a supported [Microsoft Entra role](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference?toc=%2Fgraph%2Ftoc.json) or a custom role that grants the permissions required for this operation. This operation supports the following built-in roles, which provide only the least privilege necessary:

- Global Secure Access Administrator - read standard properties
- Security Reader - read standard properties
- Security Administrator - read standard properties
- Global Reader
- Conditional Access Administrator

## HTTP request

HTTP

Copy

```http
GET /identity/conditionalAccess/policies/{id}
```

## Optional query parameters

This method supports the `$select` OData query parameter to help customize the response. For general information, see [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters).

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and the requested [conditionalAccessPolicy](https://learn.microsoft.com/en-us/graph/api/resources/conditionalaccesspolicy?view=graph-rest-1.0) object in the response body.

## Example

### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/conditionalaccesspolicy-get?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/identity/conditionalAccess/policies/10ef4fe6-5e51-4f5e-b5a2-8fed19d0be67
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Identity.ConditionalAccess.Policies["{conditionalAccessPolicy-id}"].GetAsync();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  //other-imports
)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
policies, err := graphClient.Identity().ConditionalAccess().Policies().ByConditionalAccessPolicyId("conditionalAccessPolicy-id").Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ConditionalAccessPolicy result = graphClient.identity().conditionalAccess().policies().byConditionalAccessPolicyId("{conditionalAccessPolicy-id}").get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let conditionalAccessPolicy = await client.api('/identity/conditionalAccess/policies/10ef4fe6-5e51-4f5e-b5a2-8fed19d0be67')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->identity()->conditionalAccess()->policies()->byConditionalAccessPolicyId('conditionalAccessPolicy-id')->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.SignIns

Get-MgIdentityConditionalAccessPolicy -ConditionalAccessPolicyId $conditionalAccessPolicyId
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.identity.conditional_access.policies.by_conditional_access_policy_id('conditionalAccessPolicy-id').get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identity/conditionalAccess/policies/$entity",
    "@microsoft.graph.tips": "Use $select to choose only the properties your app needs, as this can lead to performance improvements. For example: GET identity/conditionalAccess/policies('<guid>')?$select=conditions,createdDateTime",
    "id": "10ef4fe6-5e51-4f5e-b5a2-8fed19d0be67",
    "templateId": null,
    "displayName": "CA008: Require password change for high-risk users",
    "createdDateTime": "2021-11-02T14:26:29.1005248Z",
    "modifiedDateTime": "2024-01-30T23:11:08.549481Z",
    "state": "enabled",
    "conditions": {
        "userRiskLevels": [\
            "high"\
        ],
        "signInRiskLevels": [],
        "clientAppTypes": [\
            "all"\
        ],
        "servicePrincipalRiskLevels": [],
        "insiderRiskLevels": null,
        "platforms": null,
        "locations": null,
        "devices": null,
        "clientApplications": null,
        "applications": {
            "includeApplications": [\
                "All"\
            ],
            "excludeApplications": [],
            "includeUserActions": [],
            "includeAuthenticationContextClassReferences": [],
            "applicationFilter": null
        },
        "users": {
            "includeUsers": [\
                "All"\
            ],
            "excludeUsers": [],
            "includeGroups": [],
            "excludeGroups": [\
                "eedad040-3722-4bcb-bde5-bc7c857f4983"\
            ],
            "includeRoles": [],
            "excludeRoles": [],
            "includeGuestsOrExternalUsers": null,
            "excludeGuestsOrExternalUsers": null
        }
    },
    "grantControls": {
        "operator": "AND",
        "builtInControls": [\
            "passwordChange"\
        ],
        "customAuthenticationFactors": [],
        "termsOfUse": [],
        "authenticationStrength@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identity/conditionalAccess/policies('10ef4fe6-5e51-4f5e-b5a2-8fed19d0be67')/grantControls/authenticationStrength/$entity",
        "authenticationStrength": {
            "id": "00000000-0000-0000-0000-000000000002",
            "createdDateTime": "2021-12-01T08:00:00Z",
            "modifiedDateTime": "2021-12-01T08:00:00Z",
            "displayName": "Multifactor authentication",
            "description": "Combinations of methods that satisfy strong authentication, such as a password + SMS",
            "policyType": "builtIn",
            "requirementsSatisfied": "mfa",
            "allowedCombinations": [\
                "windowsHelloForBusiness",\
                "fido2",\
                "x509CertificateMultiFactor",\
                "deviceBasedPush",\
                "temporaryAccessPassOneTime",\
                "temporaryAccessPassMultiUse",\
                "password,microsoftAuthenticatorPush",\
                "password,softwareOath",\
                "password,hardwareOath",\
                "password,sms",\
                "password,voice",\
                "federatedMultiFactor",\
                "microsoftAuthenticatorPush,federatedSingleFactor",\
                "softwareOath,federatedSingleFactor",\
                "hardwareOath,federatedSingleFactor",\
                "sms,federatedSingleFactor",\
                "voice,federatedSingleFactor"\
            ],
            "combinationConfigurations@odata.context": "https://graph.microsoft.com/v1.0/$metadata#identity/conditionalAccess/policies('10ef4fe6-5e51-4f5e-b5a2-8fed19d0be67')/grantControls/authenticationStrength/combinationConfigurations",
            "combinationConfigurations": []
        }
    },
    "sessionControls": {
        "disableResilienceDefaults": null,
        "applicationEnforcedRestrictions": null,
        "cloudAppSecurity": null,
        "persistentBrowser": null,
        "signInFrequency": {
            "value": null,
            "type": null,
            "authenticationType": "primaryAndSecondaryAuthentication",
            "frequencyInterval": "everyTime",
            "isEnabled": true
        }
    }
}
```

* * *
