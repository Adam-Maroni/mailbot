# List callRecords

Namespace: microsoft.graph.callRecords

Get the list of [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) objects and their properties. The results can be optionally filtered using the `$filter` query parameter on the **startDateTime** and participant **id** properties. Note that the listed call records don't include expandable relationships such as **sessions** and **participants\_v2**. You can expand these relationships using [Get callRecord](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0) for a specific record.

Warning

A call record is created after a call or meeting ends and remains available for **30 days**. This API doesn't return call records older than 30 days.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ❌ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Not supported. | Not supported. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | CallRecords.Read.All | Not available. |

## HTTP request

HTTP

Copy

```http
GET /communications/callRecords
```

## Optional query parameters

This method supports the following OData query parameters to help customize the response. For general information, see [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters).

| Name | Description |
| --- | --- |
| $select | Use the `$select` query parameter to return a set of properties that are different than the default set for an individual resource or a collection of resources. |
| $filter | Use the `$filter` query parameter to retrieve just a subset of a collection. Only supported for the **startDateTime** (`lt`,`le`,`gt`,`ge`) and participant **participants\_v2.id** (`eq`) properties. |

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Prefer: odata.maxpagesize={x} | Specifies a preferred integer {x} page size for paginated results. This value must be equal to or less than the maximum allowable page size. Optional. |
| Prefer: include-unknown-enum-members | Enables evolvable enum values beyond the sentinel value. For more information, see [Best practices for working with Microsoft Graph](https://learn.microsoft.com/en-us/graph/best-practices-concept#handling-future-members-in-evolvable-enumerations). Optional. |
| Prefer: omit-values=nulls | Removes null or empty values from the response. Optional. |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a collection of [microsoft.graph.callRecords.callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) objects in the response body.

When a result set spans multiple pages, Microsoft Graph returns that page with an **@odata.nextLink** property in the response that contains a URL to the next page of results. If that property is present, continue making additional requests with the **@odata.nextLink** URL in each response, until all the results are returned. For more information, see [Paging Microsoft Graph data in your app](https://learn.microsoft.com/en-us/graph/paging). The default page size for call records is 60 entries.

## Examples

### Example 1: List all records

The following example shows how to get all [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) objects.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [Python](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/communications/callRecords
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Communications.CallRecords.GetAsync();
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
callRecords, err := graphClient.Communications().CallRecords().Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.callrecords.CallRecordCollectionResponse result = graphClient.communications().callRecords().get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let callRecords = await client.api('/communications/callRecords')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->communications()->callRecords()->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.communications.call_records.get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords",
  "value": [\
    {\
      "id": "3cf3bbc8-b21d-4f2e-bfd0-b13603ae6c65",\
      "version": 2,\
      "type": "unknown",\
      "modalities": [\
        "audio"\
      ],\
      "lastModifiedDateTime": "2023-09-25T10:36:40Z",\
      "startDateTime": "2023-09-25T09:28:38Z",\
      "endDateTime": "2023-09-25T09:28:41Z",\
      "organizer": {\
        "user": {\
          "id": "821809f5-0000-0000-0000-3b5136c0e777",\
          "displayName": "Abbie Wilkins",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
        }\
      },\
      "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('3cf3bbc8-b21d-4f2e-bfd0-b13603ae6c65')/organizer_v2/$entity",\
      "organizer_v2": {\
        "id": "821809f5-0000-0000-0000-3b5136c0e777",\
        "identity": {\
          "user": {\
            "id": "821809f5-0000-0000-0000-3b5136c0e777",\
            "displayName": "Abbie Wilkins",\
            "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
          }\
        }\
      }\
    },\
    {\
      "id": "c3ad8c4b-4a87-4ab1-bef0-284d2f40ed9f",\
      "version": 2,\
      "type": "unknown",\
      "modalities": [\
        "audio"\
      ],\
      "lastModifiedDateTime": "2023-09-25T14:18:13Z",\
      "startDateTime": "2023-09-25T14:03:36Z",\
      "endDateTime": "2023-09-25T14:03:40Z",\
      "organizer": {\
        "user": {\
          "id": "821809f5-0000-0000-0000-3b5136c0e777",\
          "displayName": "Abbie Wilkins",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
        }\
      },\
      "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('c3ad8c4b-4a87-4ab1-bef0-284d2f40ed9f')/organizer_v2/$entity",\
      "organizer_v2": {\
        "id": "+5564981205182",\
        "identity": {\
          "user": null,\
          "acsUser": null,\
          "spoolUser": null,\
          "phone": {\
            "id": "+5564981205182",\
            "displayName": null,\
            "tenantId": null\
          }\
        }\
      }\
    }\
  ]
}
```

### Example 2: Filter by startDateTime

The following example shows how to get [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) objects filtered by the **startDateTime** property.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [Python](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/communications/callRecords?$filter=startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Communications.CallRecords.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z";
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
	  graphcommunications "github.com/microsoftgraph/msgraph-sdk-go/communications"
	  //other-imports
)

requestFilter := "startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z"

requestParameters := &graphcommunications.CommunicationsCallRecordsRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
}
configuration := &graphcommunications.CommunicationsCallRecordsRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
callRecords, err := graphClient.Communications().CallRecords().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.callrecords.CallRecordCollectionResponse result = graphClient.communications().callRecords().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z";
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

let callRecords = await client.api('/communications/callRecords')
	.filter('startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Communications\CallRecords\CallRecordsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new CallRecordsRequestBuilderGetRequestConfiguration();
$queryParameters = CallRecordsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->communications()->callRecords()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.communications.call_records.call_records_request_builder import CallRecordsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = CallRecordsRequestBuilder.CallRecordsRequestBuilderGetQueryParameters(
		filter = "startDateTime ge 2023-09-25T09:25:00Z and startDateTime lt 2023-09-25T09:30:00Z",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.communications.call_records.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords",
  "value": [\
    {\
      "id": "3cf3bbc8-b21d-4f2e-bfd0-b13603ae6c65",\
      "version": 2,\
      "type": "unknown",\
      "modalities": [\
        "audio"\
      ],\
      "lastModifiedDateTime": "2023-09-25T10:36:40Z",\
      "startDateTime": "2023-09-25T09:28:38Z",\
      "endDateTime": "2023-09-25T09:28:41Z",\
      "organizer": {\
        "user": {\
          "id": "821809f5-0000-0000-0000-3b5136c0e777",\
          "displayName": "Abbie Wilkins",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
        }\
      },\
      "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('3cf3bbc8-b21d-4f2e-bfd0-b13603ae6c65')/organizer_v2/$entity",\
      "organizer_v2": {\
        "id": "821809f5-0000-0000-0000-3b5136c0e777",\
        "identity": {\
          "user": {\
            "id": "821809f5-0000-0000-0000-3b5136c0e777",\
            "displayName": "Abbie Wilkins",\
            "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
          }\
        }\
      }\
    }\
  ]
}
```

### Example 3: Filter by participant ID

The following example shows how to get [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) objects filtered by the **id** property of a [participant](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-participant?view=graph-rest-1.0).

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_php)
- [Python](https://learn.microsoft.com/en-us/graph/api/callrecords-cloudcommunications-list-callrecords?view=graph-rest-1.0&tabs=http#tabpanel_3_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/communications/callRecords?$filter=participants_v2/any(p:p/id eq '821809f5-0000-0000-0000-3b5136c0e777')
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Communications.CallRecords.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "participants_v2/any(p:p/id eq '821809f5-0000-0000-0000-3b5136c0e777')";
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
	  graphcommunications "github.com/microsoftgraph/msgraph-sdk-go/communications"
	  //other-imports
)

requestFilter := "participants_v2/any(p:p/id eq '821809f5-0000-0000-0000-3b5136c0e777')"

requestParameters := &graphcommunications.CommunicationsCallRecordsRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
}
configuration := &graphcommunications.CommunicationsCallRecordsRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
callRecords, err := graphClient.Communications().CallRecords().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.callrecords.CallRecordCollectionResponse result = graphClient.communications().callRecords().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "participants_v2/any(p:p/id eq '821809f5-0000-0000-0000-3b5136c0e777')";
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

let callRecords = await client.api('/communications/callRecords')
	.filter('participants_v2/any(p:p/id eq \'821809f5-0000-0000-0000-3b5136c0e777\')')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Communications\CallRecords\CallRecordsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new CallRecordsRequestBuilderGetRequestConfiguration();
$queryParameters = CallRecordsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "participants_v2/any(p:p/id eq '821809f5-0000-0000-0000-3b5136c0e777')";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->communications()->callRecords()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.communications.call_records.call_records_request_builder import CallRecordsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = CallRecordsRequestBuilder.CallRecordsRequestBuilderGetQueryParameters(
		filter = "participants_v2/any(p:p/id eq '821809f5-0000-0000-0000-3b5136c0e777')",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.communications.call_records.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords",
  "value": [\
    {\
      "id": "3cf3bbc8-b21d-4f2e-bfd0-b13603ae6c65",\
      "version": 2,\
      "type": "unknown",\
      "modalities": [\
        "audio"\
      ],\
      "lastModifiedDateTime": "2023-09-25T10:36:40Z",\
      "startDateTime": "2023-09-25T09:28:38Z",\
      "endDateTime": "2023-09-25T09:28:41Z",\
      "organizer": {\
        "user": {\
          "id": "821809f5-0000-0000-0000-3b5136c0e777",\
          "displayName": "Abbie Wilkins",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
        }\
      },\
      "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('3cf3bbc8-b21d-4f2e-bfd0-b13603ae6c65')/organizer_v2/$entity",\
      "organizer_v2": {\
        "id": "821809f5-0000-0000-0000-3b5136c0e777",\
        "identity": {\
          "user": {\
            "id": "821809f5-0000-0000-0000-3b5136c0e777",\
            "displayName": "Abbie Wilkins",\
            "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"\
          }\
        }\
      }\
    }\
  ]
}
```

## See also

For more information on using call records, see [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0).

* * *
