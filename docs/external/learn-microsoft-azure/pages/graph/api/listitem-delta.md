# listItem: delta

Namespace: microsoft.graph

Get newly created, updated, or deleted [list items](https://learn.microsoft.com/en-us/graph/api/resources/listitem?view=graph-rest-1.0) without having to perform a full read of the entire items collection.

Your app begins by calling `delta` without any parameters.
The service starts enumerating the hierarchy of the list, returning pages of items, and either an **@odata.nextLink** or an **@odata.deltaLink**.
Your app should continue calling with the **@odata.nextLink** until you see an **@odata.deltaLink** returned.

After you received all the changes, you can apply them to your local state.
To check for changes in the future, call `delta` again with the **@odata.deltaLink** from the previous response.

The delta feed shows the latest state for each item, not each change. If an item was renamed twice, it only shows up once, with its latest name.
The same item might appear more than once in a delta feed, for various reasons. You should use the last occurrence you see.

Items with this property should be removed from your local state.

> **Note:** You should only delete a folder locally if it's empty after syncing all the changes.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Sites.Read.All | Sites.ReadWrite.All |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | Sites.Read.All | Sites.ReadWrite.All |

## HTTP request

HTTP

Copy

```http
GET /sites/{siteId}/lists/{listId}/items/delta
```

## Query parameters

In the request URL, you can include the following optional query parameter.

| Parameter | Type | Description |
| --- | --- | --- |
| token | String | If unspecified, enumerates the current state of the hierarchy. If `latest`, returns an empty response with the latest delta token. If a previous delta token, returns a new state since that token. |

This method also supports the `$select`, `$expand`, and `$top` [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters) to customize the response.

## Request headers

| Header | Value |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a collection of [listItem](https://learn.microsoft.com/en-us/graph/api/resources/listitem?view=graph-rest-1.0) objects in the response body.

In addition to a collection of **listItem** objects, the response also includes one of the following properties.

| Name | Value | Description |
| --- | --- | --- |
| @odata.nextLink | URL | A URL to retrieve the next available page of changes if there are more changes in the current set. |
| @odata.deltaLink | URL | A URL returned instead of **@odata.nextLink** after all current changes have been returned. Use this property to read the next set of changes in the future. |

In some cases, the service returns a `410 Gone` response code with an error response that contains one of the following error codes, and a `Location` header that contains a new `nextLink` that starts a fresh delta enumeration. This occurs when the service can't provide a list of changes for a given token; for example, if a client tries to reuse an old token after being disconnected for a long time, or if the server state has changed and a new token is required.

After the full enumeration is completed, compare the returned items with your local state and follow the instructions based on the error type.

| Error type | Instructions |
| --- | --- |
| resyncChangesApplyDifferences | Replace any local items with the versions from the server (including deletes) if you're sure that the service was up-to-date with your local changes when you last synchronized. Upload any local changes that the server doesn't know about. |
| resyncChangesUploadDifferences | Upload any local items that the service didn't return and upload any items that differ from the versions from the server. Keep both copies if you're not sure which one is more up-to-date. |

In addition to the resync errors and for more details about how errors are returned, see [Microsoft Graph error responses and resource types](https://learn.microsoft.com/en-us/graph/errors).

## Examples

### Example 1: Initial request

The following example shows an initial request and how to call this API to establish your local state.

#### Request

The following example shows an initial request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Sites["{site-id}"].Lists["{list-id}"].Items.Delta.GetAsDeltaGetResponseAsync();
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
delta, err := graphClient.Sites().BySiteId("site-id").Lists().ByListId("list-id").Items().Delta().GetAsDeltaGetResponse(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

var result = graphClient.sites().bySiteId("{site-id}").lists().byListId("{list-id}").items().delta().get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let delta = await client.api('/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->sites()->bySiteId('site-id')->lists()->byListId('list-id')->items()->delta()->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Sites

Get-MgSiteListItemDelta -SiteId $siteId -ListId $listId
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.sites.by_site_id('site-id').lists.by_list_id('list-id').items.delta.get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response that includes the first page of changes and the **@odata.nextLink** property that indicates that no more items are available in the current set of items. Your app should continue to request the URL value of **@odata.nextLink** until all pages of items have been retrieved.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "value": [\
    {\
      "createdDateTime": "2020-06-02T22:46:58Z",\
      "eTag": "\"{12AD05BB-59B8-43AA-9456-77C44E9BC066},756\"",\
      "id": "1",\
      "lastModifiedDateTime": "2021-10-14T23:27:27Z",\
      "webUrl": "http://contoso.sharepoint.com/Shared%20Documents/TestFolder",\
      "createdBy": {\
        "user": {\
          "displayName": "John doe"\
        }\
      },\
      "parentReference": {\
        "id": "1",\
        "path": "Shared%20Documents",\
        "siteId": "12AD05BB-59B8-43AA-9456-77C44E9BC066"\
      },\
      "contentType": {\
        "id": "0x00123456789abc",\
        "name": "Folder"\
      }\
    },\
    {\
      "createdDateTime": "2020-06-02T22:46:58Z",\
      "eTag": "\"{12AD05BB-59B8-43AA-9456-77C44E9BC067},756\"",\
      "id": "2",\
      "lastModifiedDateTime": "2021-10-14T23:27:27Z",\
      "webUrl": "http://contoso.sharepoint.com/Shared%20Documents/TestItemA.txt",\
      "createdBy": {\
        "user": {\
          "displayName": "John doe"\
        }\
      },\
      "parentReference": {\
        "id": "2",\
        "path": "Shared%20Documents",\
        "siteId": "12AD05BB-59B8-43AA-9456-77C44E9BC066"\
      },\
      "contentType": {\
        "id": "0x00123456789abc",\
        "name": "Document"\
      }\
    },\
    {\
      "createdDateTime": "2020-06-02T22:46:58Z",\
      "eTag": "\"{12AD05BB-59B8-43AA-9456-77C44E9BC068},756\"",\
      "id": "3",\
      "lastModifiedDateTime": "2021-10-14T23:27:27Z",\
      "webUrl": "http://contoso.sharepoint.com/Shared%20Documents/TestItemB.txt",\
      "createdBy": {\
        "user": {\
          "displayName": "John doe"\
        }\
      },\
      "parentReference": {\
        "id": "3",\
        "path": "Shared%20Documents",\
        "siteId": "12AD05BB-59B8-43AA-9456-77C44E9BC066"\
      },\
      "contentType": {\
        "id": "0x00123456789abc",\
        "name": "Document"\
      }\
    }\
  ],
  "@odata.nextLink": "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=1230919asd190410jlka"
}
```

### Example 2: Last page request

The following example shows a request that gets the last page in a set and how to call this API to update your local state.

#### Request

The following example shows a request after the initial request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=1230919asd190410jlka
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Sites["{site-id}"].Lists["{list-id}"].Items.Delta.GetAsDeltaGetResponseAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Token = "1230919asd190410jlka";
});
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
	  graphsites "github.com/microsoftgraph/msgraph-sdk-go/sites"
	  //other-imports
)

requestToken := "1230919asd190410jlka"

requestParameters := &graphsites.ItemListsItemItemsDeltaRequestBuilderGetQueryParameters{
	Token: &requestToken,
}
configuration := &graphsites.ItemListsItemItemsDeltaRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
delta, err := graphClient.Sites().BySiteId("site-id").Lists().ByListId("list-id").Items().Delta().GetAsDeltaGetResponse(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

var result = graphClient.sites().bySiteId("{site-id}").lists().byListId("{list-id}").items().delta().get(requestConfiguration -> {
	requestConfiguration.queryParameters.token = "1230919asd190410jlka";
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let delta = await client.api('/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=1230919asd190410jlka')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Sites\Item\Lists\Item\Items\Delta\DeltaRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new DeltaRequestBuilderGetRequestConfiguration();
$queryParameters = DeltaRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->token = "1230919asd190410jlka";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->sites()->bySiteId('site-id')->lists()->byListId('list-id')->items()->delta()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Sites

Get-MgSiteListItemDelta -SiteId $siteId -ListId $listId -Token "1230919asd190410jlka"
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.sites.item.lists.item.items.delta.delta_request_builder import DeltaRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = DeltaRequestBuilder.DeltaRequestBuilderGetQueryParameters(
		token = "1230919asd190410jlka",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.sites.by_site_id('site-id').lists.by_list_id('list-id').items.delta.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response that indicates that the item named `TestItemB.txt` was deleted and the item `TestFolder` was either added or modified between the initial request and this request to update the local state.

The final page of items includes the **@odata.deltaLink** property that provides the URL that can be used later to retrieve changes since the current set of items.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "value": [\
    {\
      "createdDateTime": "2020-06-02T22:46:58Z",\
      "eTag": "\"{12AD05BB-59B8-43AA-9456-77C44E9BC066},756\"",\
      "id": "1",\
      "lastModifiedDateTime": "2016-03-21T20:01:37Z",\
      "webUrl": "http://contoso.sharepoint.com/Shared%20Documents/TestFolder",\
      "createdBy": {\
        "user": {\
          "displayName": "John doe"\
        }\
      },\
      "parentReference": {\
        "id": "1",\
        "path": "Shared%20Documents",\
        "siteId": "12AD05BB-59B8-43AA-9456-77C44E9BC066"\
      },\
      "contentType": {\
        "id": "0x00123456789abc",\
        "name": "Folder"\
      }\
    },\
    {\
      "id": "3",\
      "parentReference": {\
        "siteId": "12AD05BB-59B8-43AA-9456-77C44E9BC066"\
      },\
      "contentType": {\
        "id": "0x00123456789abc",\
        "name": "Document"\
      },\
      "deleted": {\
        "state": "deleted"\
      }\
    }\
  ],
  "@odata.deltaLink": "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=1230919asd190410jlka"
}
```

### Example 3: Delta link request

In some scenarios, you might want to request the current `deltaLink` value without first enumerating all of the items in the list already. This can be useful if your app only wants to know about changes and doesn't need to know about existing items.
To retrieve the latest `deltaLink`, call `delta` with the query string parameter `?token=latest`.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/listitem-delta?view=graph-rest-1.0&tabs=http#tabpanel_3_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=latest
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Sites["{site-id}"].Lists["{list-id}"].Items.Delta.GetAsDeltaGetResponseAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Token = "latest";
});
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
	  graphsites "github.com/microsoftgraph/msgraph-sdk-go/sites"
	  //other-imports
)

requestToken := "latest"

requestParameters := &graphsites.ItemListsItemItemsDeltaRequestBuilderGetQueryParameters{
	Token: &requestToken,
}
configuration := &graphsites.ItemListsItemItemsDeltaRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
delta, err := graphClient.Sites().BySiteId("site-id").Lists().ByListId("list-id").Items().Delta().GetAsDeltaGetResponse(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

var result = graphClient.sites().bySiteId("{site-id}").lists().byListId("{list-id}").items().delta().get(requestConfiguration -> {
	requestConfiguration.queryParameters.token = "latest";
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let delta = await client.api('/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=latest')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Sites\Item\Lists\Item\Items\Delta\DeltaRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new DeltaRequestBuilderGetRequestConfiguration();
$queryParameters = DeltaRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->token = "latest";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->sites()->bySiteId('site-id')->lists()->byListId('list-id')->items()->delta()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Sites

Get-MgSiteListItemDelta -SiteId $siteId -ListId $listId -Token "latest"
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.sites.item.lists.item.items.delta.delta_request_builder import DeltaRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = DeltaRequestBuilder.DeltaRequestBuilderGetQueryParameters(
		token = "latest",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.sites.by_site_id('site-id').lists.by_list_id('list-id').items.delta.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "value": [ ],
  "@odata.deltaLink": "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,2C712604-1370-44E7-A1F5-426573FDA80A,2D2244C3-251A-49EA-93A8-39E1C3A060FE/lists/22e03ef3-6ef4-424d-a1d3-92a337807c30/items/delta?token=1230919asd190410jlka"
}
```

## Related content

- [Use delta query to track changes in Microsoft Graph data](https://learn.microsoft.com/en-us/graph/delta-query-overview)
- [Best practices for discovering files and detecting changes at scale](https://learn.microsoft.com/en-us/onedrive/developer/rest-api/concepts/scan-guidance)

* * *
