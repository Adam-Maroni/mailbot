# Add synchronization secrets

Namespace: microsoft.graph

Provide credentials for establishing connectivity with the target system.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Synchronization.ReadWrite.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | Application.ReadWrite.OwnedBy | Synchronization.ReadWrite.All |

Important

For delegated access using work or school accounts, the signed-in user must be an owner or member of the group or be assigned a supported [Microsoft Entra role](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference?toc=%2Fgraph%2Ftoc.json) or a custom role that grants the permissions required for this operation. This operation supports the following built-in roles, which provide only the least privilege necessary:

- Application Administrator
- Cloud Application Administrator
- Hybrid Identity Administrator - to configure Microsoft Entra Cloud Sync

## HTTP request

HTTP

Copy

```http
PUT /servicePrincipals/{id}/synchronization/secrets
```

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

In the request body, provide a JSON object with the following parameters.

| Parameter | Type | Description |
| --- | --- | --- |
| credentials | [synchronizationSecretKeyStringValuePair](https://learn.microsoft.com/en-us/graph/api/resources/synchronization-synchronizationsecretkeystringvaluepair?view=graph-rest-1.0) collection | Credentials to validate. Ignored when the **useSavedCredentials** parameter is `true`. |

## Response

If the secrets are successfully saved, this method returns a `204 No Content` response code. It doesn't return anything in the response body.

## Example

### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/synchronization-serviceprincipal-put-synchronization?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
PUT https://graph.microsoft.com/v1.0/servicePrincipals/{id}/synchronization/secrets
Content-type: application/json

{
    "value": [\
        {\
            "key": "BaseAddress",\
            "value": "user@domain.com"\
        },\
        {\
            "key": "SecretToken",\
            "value": "password-value"\
        },\
        {\
            "key": "SyncNotificationSettings",\
            "value": "{\"Enabled\":false,\"DeleteThresholdEnabled\":false}"\
        },\
        {\
            "key": "SyncAll",\
            "value": "false"\
        }\
    ]
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.ServicePrincipals.Item.Synchronization.Secrets;
using Microsoft.Graph.Models;

var requestBody = new SecretsPutRequestBody
{
	Value = new List<SynchronizationSecretKeyStringValuePair>
	{
		new SynchronizationSecretKeyStringValuePair
		{
			Key = SynchronizationSecret.BaseAddress,
			Value = "user@domain.com",
		},
		new SynchronizationSecretKeyStringValuePair
		{
			Key = SynchronizationSecret.SecretToken,
			Value = "password-value",
		},
		new SynchronizationSecretKeyStringValuePair
		{
			Key = SynchronizationSecret.SyncNotificationSettings,
			Value = "{\"Enabled\":false,\"DeleteThresholdEnabled\":false}",
		},
		new SynchronizationSecretKeyStringValuePair
		{
			Key = SynchronizationSecret.SyncAll,
			Value = "false",
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].Synchronization.Secrets.PutAsSecretsPutResponseAsync(requestBody);
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
	  graphserviceprincipals "github.com/microsoftgraph/msgraph-sdk-go/serviceprincipals"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphserviceprincipals.NewSecretsPutRequestBody()

synchronizationSecretKeyStringValuePair := graphmodels.NewSynchronizationSecretKeyStringValuePair()
key := graphmodels.BASEADDRESS_SYNCHRONIZATIONSECRET
synchronizationSecretKeyStringValuePair.SetKey(&key)
value := "user@domain.com"
synchronizationSecretKeyStringValuePair.SetValue(&value)
synchronizationSecretKeyStringValuePair1 := graphmodels.NewSynchronizationSecretKeyStringValuePair()
key := graphmodels.SECRETTOKEN_SYNCHRONIZATIONSECRET
synchronizationSecretKeyStringValuePair1.SetKey(&key)
value := "password-value"
synchronizationSecretKeyStringValuePair1.SetValue(&value)
synchronizationSecretKeyStringValuePair2 := graphmodels.NewSynchronizationSecretKeyStringValuePair()
key := graphmodels.SYNCNOTIFICATIONSETTINGS_SYNCHRONIZATIONSECRET
synchronizationSecretKeyStringValuePair2.SetKey(&key)
value := "{\"Enabled\":false,\"DeleteThresholdEnabled\":false}"
synchronizationSecretKeyStringValuePair2.SetValue(&value)
synchronizationSecretKeyStringValuePair3 := graphmodels.NewSynchronizationSecretKeyStringValuePair()
key := graphmodels.SYNCALL_SYNCHRONIZATIONSECRET
synchronizationSecretKeyStringValuePair3.SetKey(&key)
value := "false"
synchronizationSecretKeyStringValuePair3.SetValue(&value)

value := []graphmodels.SynchronizationSecretKeyStringValuePairable {
	synchronizationSecretKeyStringValuePair,
	synchronizationSecretKeyStringValuePair1,
	synchronizationSecretKeyStringValuePair2,
	synchronizationSecretKeyStringValuePair3,
}
requestBody.SetValue(value)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
secrets, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").Synchronization().Secrets().PutAsSecretsPutResponse(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.serviceprincipals.item.synchronization.secrets.SecretsPutRequestBody secretsPutRequestBody = new com.microsoft.graph.serviceprincipals.item.synchronization.secrets.SecretsPutRequestBody();
LinkedList<SynchronizationSecretKeyStringValuePair> value = new LinkedList<SynchronizationSecretKeyStringValuePair>();
SynchronizationSecretKeyStringValuePair synchronizationSecretKeyStringValuePair = new SynchronizationSecretKeyStringValuePair();
synchronizationSecretKeyStringValuePair.setKey(SynchronizationSecret.BaseAddress);
synchronizationSecretKeyStringValuePair.setValue("user@domain.com");
value.add(synchronizationSecretKeyStringValuePair);
SynchronizationSecretKeyStringValuePair synchronizationSecretKeyStringValuePair1 = new SynchronizationSecretKeyStringValuePair();
synchronizationSecretKeyStringValuePair1.setKey(SynchronizationSecret.SecretToken);
synchronizationSecretKeyStringValuePair1.setValue("password-value");
value.add(synchronizationSecretKeyStringValuePair1);
SynchronizationSecretKeyStringValuePair synchronizationSecretKeyStringValuePair2 = new SynchronizationSecretKeyStringValuePair();
synchronizationSecretKeyStringValuePair2.setKey(SynchronizationSecret.SyncNotificationSettings);
synchronizationSecretKeyStringValuePair2.setValue("{\"Enabled\":false,\"DeleteThresholdEnabled\":false}");
value.add(synchronizationSecretKeyStringValuePair2);
SynchronizationSecretKeyStringValuePair synchronizationSecretKeyStringValuePair3 = new SynchronizationSecretKeyStringValuePair();
synchronizationSecretKeyStringValuePair3.setKey(SynchronizationSecret.SyncAll);
synchronizationSecretKeyStringValuePair3.setValue("false");
value.add(synchronizationSecretKeyStringValuePair3);
secretsPutRequestBody.setValue(value);
var result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").synchronization().secrets().put(secretsPutRequestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const secrets = {
    value: [\
        {\
            key: 'BaseAddress',\
            value: 'user@domain.com'\
        },\
        {\
            key: 'SecretToken',\
            value: 'password-value'\
        },\
        {\
            key: 'SyncNotificationSettings',\
            value: '{\"Enabled\':false,\'DeleteThresholdEnabled\':false}"\
        },\
        {\
            key: 'SyncAll',\
            value: 'false'\
        }\
    ]
};

await client.api('/servicePrincipals/{id}/synchronization/secrets')
	.put(secrets);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\ServicePrincipals\Item\Synchronization\Secrets\SecretsPutRequestBody;
use Microsoft\Graph\Generated\Models\SynchronizationSecretKeyStringValuePair;
use Microsoft\Graph\Generated\Models\SynchronizationSecret;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new SecretsPutRequestBody();
$valueSynchronizationSecretKeyStringValuePair1 = new SynchronizationSecretKeyStringValuePair();
$valueSynchronizationSecretKeyStringValuePair1->setKey(new SynchronizationSecret('baseAddress'));
$valueSynchronizationSecretKeyStringValuePair1->setValue('user@domain.com');
$valueArray []= $valueSynchronizationSecretKeyStringValuePair1;
$valueSynchronizationSecretKeyStringValuePair2 = new SynchronizationSecretKeyStringValuePair();
$valueSynchronizationSecretKeyStringValuePair2->setKey(new SynchronizationSecret('secretToken'));
$valueSynchronizationSecretKeyStringValuePair2->setValue('password-value');
$valueArray []= $valueSynchronizationSecretKeyStringValuePair2;
$valueSynchronizationSecretKeyStringValuePair3 = new SynchronizationSecretKeyStringValuePair();
$valueSynchronizationSecretKeyStringValuePair3->setKey(new SynchronizationSecret('syncNotificationSettings'));
$valueSynchronizationSecretKeyStringValuePair3->setValue('{\"Enabled\":false,\"DeleteThresholdEnabled\":false}');
$valueArray []= $valueSynchronizationSecretKeyStringValuePair3;
$valueSynchronizationSecretKeyStringValuePair4 = new SynchronizationSecretKeyStringValuePair();
$valueSynchronizationSecretKeyStringValuePair4->setKey(new SynchronizationSecret('syncAll'));
$valueSynchronizationSecretKeyStringValuePair4->setValue('false');
$valueArray []= $valueSynchronizationSecretKeyStringValuePair4;
$requestBody->setValue($valueArray);

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->synchronization()->secrets()->put($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	value = @(
		@{
			key = "BaseAddress"
			value = "user@domain.com"
		}
		@{
			key = "SecretToken"
			value = "password-value"
		}
		@{
			key = "SyncNotificationSettings"
			value = '{"Enabled":false,"DeleteThresholdEnabled":false}'
		}
		@{
			key = "SyncAll"
			value = "false"
		}
	)
}

Set-MgServicePrincipalSynchronizationSecret -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.serviceprincipals.item.synchronization.secrets.secrets_put_request_body import SecretsPutRequestBody
from msgraph.generated.models.synchronization_secret_key_string_value_pair import SynchronizationSecretKeyStringValuePair
from msgraph.generated.models.synchronization_secret import SynchronizationSecret
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = SecretsPutRequestBody(
	value = [\
		SynchronizationSecretKeyStringValuePair(\
			key = SynchronizationSecret.BaseAddress,\
			value = "user@domain.com",\
		),\
		SynchronizationSecretKeyStringValuePair(\
			key = SynchronizationSecret.SecretToken,\
			value = "password-value",\
		),\
		SynchronizationSecretKeyStringValuePair(\
			key = SynchronizationSecret.SyncNotificationSettings,\
			value = "{\"Enabled\":false,\"DeleteThresholdEnabled\":false}",\
		),\
		SynchronizationSecretKeyStringValuePair(\
			key = SynchronizationSecret.SyncAll,\
			value = "false",\
		),\
	],
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').synchronization.secrets.put(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 204 No Content
```

* * *
