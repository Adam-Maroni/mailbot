# user: translateExchangeIds

Namespace: microsoft.graph

Translate identifiers of Outlook-related resources between formats.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ❌ | ❌ | ✅ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | User.ReadBasic.All | AgentIdUser.ReadWrite.All, AgentIdUser.ReadWrite.IdentityParentedBy, User.Read, User.Read.All, User.ReadWrite, User.ReadWrite.All |
| Delegated (personal Microsoft account) | User.Read | User.ReadWrite |
| Application | Not supported. | Not supported. |

## HTTP request

HTTP

Copy

```http
POST /me/translateExchangeIds
POST /users/{id|userPrincipalName}/translateExchangeIds
```

## Request headers

| Name | Value |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

| Parameter | Type | Description |
| --- | --- | --- |
| inputIds | String collection | A collection of identifiers to convert. All identifiers in the collection MUST have the same source ID type, and MUST be for items in the same mailbox. Maximum size of this collection is 1000 strings. |
| sourceIdType | exchangeIdFormat | The ID type of the identifiers in the `InputIds` parameter. |
| targetIdType | exchangeIdFormat | The requested ID type to convert to. |

### exchangeIdFormat values

| Member | Description |
| --- | --- |
| entryId | The binary entry ID format used by MAPI clients. |
| ewsId | The ID format used by Exchange Web Services clients. |
| immutableEntryId | The binary MAPI-compatible immutable ID format. |
| restId | The default ID format used by Microsoft Graph. |
| restImmutableEntryId | The immutable ID format used by Microsoft Graph. |

The binary formats (`entryId` and `immutableEntryId`) are URL-safe base64 encoded. URL-safeness is implemented by modifying the base64 encoding of the binary data in the following way:

- Replace `+` with `-`
- Replace `/` with `_`
- Remove any trailing padding characters (`=`)
- Add an integer to the end of the string indicating how many padding characters were in the original (`0`, `1`, or `2`)

## Response

If successful, this method returns `200 OK` response code and a [convertIdResult](https://learn.microsoft.com/en-us/graph/api/resources/convertidresult?view=graph-rest-1.0) collection in the response body.

## Example

The following example shows how to convert multiple identifiers from the normal REST API format (`restId`) to the REST immutable format (`restImmutableEntryId`).

### Request

Here is the example request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/me/translateExchangeIds
Content-Type: application/json

{
  "inputIds" : [\
    "{rest-formatted-id-1}",\
    "{rest-formatted-id-2}"\
  ],
  "sourceIdType": "restId",
  "targetIdType": "restImmutableEntryId"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Me.TranslateExchangeIds;
using Microsoft.Graph.Models;

var requestBody = new TranslateExchangeIdsPostRequestBody
{
	InputIds = new List<string>
	{
		"{rest-formatted-id-1}",
		"{rest-formatted-id-2}",
	},
	SourceIdType = ExchangeIdFormat.RestId,
	TargetIdType = ExchangeIdFormat.RestImmutableEntryId,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Me.TranslateExchangeIds.PostAsTranslateExchangeIdsPostResponseAsync(requestBody);
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
	  graphusers "github.com/microsoftgraph/msgraph-sdk-go/users"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphusers.NewItemTranslateExchangeIdsPostRequestBody()
inputIds := []string {
	"{rest-formatted-id-1}",
	"{rest-formatted-id-2}",
}
requestBody.SetInputIds(inputIds)
sourceIdType := graphmodels.RESTID_EXCHANGEIDFORMAT
requestBody.SetSourceIdType(&sourceIdType)
targetIdType := graphmodels.RESTIMMUTABLEENTRYID_EXCHANGEIDFORMAT
requestBody.SetTargetIdType(&targetIdType)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
translateExchangeIds, err := graphClient.Me().TranslateExchangeIds().PostAsTranslateExchangeIdsPostResponse(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.users.item.translateexchangeids.TranslateExchangeIdsPostRequestBody translateExchangeIdsPostRequestBody = new com.microsoft.graph.users.item.translateexchangeids.TranslateExchangeIdsPostRequestBody();
LinkedList<String> inputIds = new LinkedList<String>();
inputIds.add("{rest-formatted-id-1}");
inputIds.add("{rest-formatted-id-2}");
translateExchangeIdsPostRequestBody.setInputIds(inputIds);
translateExchangeIdsPostRequestBody.setSourceIdType(ExchangeIdFormat.RestId);
translateExchangeIdsPostRequestBody.setTargetIdType(ExchangeIdFormat.RestImmutableEntryId);
var result = graphClient.me().translateExchangeIds().post(translateExchangeIdsPostRequestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const convertIdResult = {
  inputIds: [\
    '{rest-formatted-id-1}',\
    '{rest-formatted-id-2}'\
  ],
  sourceIdType: 'restId',
  targetIdType: 'restImmutableEntryId'
};

await client.api('/me/translateExchangeIds')
	.post(convertIdResult);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Users\Item\TranslateExchangeIds\TranslateExchangeIdsPostRequestBody;
use Microsoft\Graph\Generated\Models\ExchangeIdFormat;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new TranslateExchangeIdsPostRequestBody();
$requestBody->setInputIds(['{rest-formatted-id-1}', '{rest-formatted-id-2}', 	]);
$requestBody->setSourceIdType(new ExchangeIdFormat('restId'));
$requestBody->setTargetIdType(new ExchangeIdFormat('restImmutableEntryId'));

$result = $graphServiceClient->me()->translateExchangeIds()->post($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Users.Actions

$params = @{
	inputIds = @(
	'{rest-formatted-id-1}'
'{rest-formatted-id-2}'
)
sourceIdType = "restId"
targetIdType = "restImmutableEntryId"
}

# A UPN can also be used as -UserId.
Invoke-MgTranslateUserExchangeId -UserId $userId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.users.item.translate_exchange_ids.translate_exchange_ids_post_request_body import TranslateExchangeIdsPostRequestBody
from msgraph.generated.models.exchange_id_format import ExchangeIdFormat
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = TranslateExchangeIdsPostRequestBody(
	input_ids = [\
		"{rest-formatted-id-1}",\
		"{rest-formatted-id-2}",\
	],
	source_id_type = ExchangeIdFormat.RestId,
	target_id_type = ExchangeIdFormat.RestImmutableEntryId,
)

result = await graph_client.me.translate_exchange_ids.post(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

Here is the example response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "value": [\
    {\
      "sourceId": "{rest-formatted-id-1}",\
      "targetId": "{rest-immutable-formatted-id-1}"\
    },\
    {\
      "sourceId": "{rest-formatted-id-2}",\
      "targetId": "{rest-immutable-formatted-id-2}"\
    }\
  ]
}
```

* * *
