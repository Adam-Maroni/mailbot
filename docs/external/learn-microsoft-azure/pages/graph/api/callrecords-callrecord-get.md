# Get callRecord

Namespace: microsoft.graph.callRecords

Retrieve the properties and relationships of a [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) object.

You can get the **id** of a **callRecord** in two ways:

- Subscribe to [change notifications](https://learn.microsoft.com/en-us/graph/api/resources/change-notifications-api-overview) to the `/communications/callRecords` endpoint.
- Use the **callChainId** property of a [call](https://learn.microsoft.com/en-us/graph/api/resources/call?view=graph-rest-1.0). The call record is available only after the associated call is completed.

Warning

A call record is created after a call or meeting ends and remains available for **30 days**. This API doesn't return call records older than 30 days, and requests for such records result in a `404 Not Found` response code.

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
GET /communications/callRecords/{id}
```

Caution

- This API doesn't currently return a record of participants who stream a live event.

## Optional query parameters

This method supports the following OData query parameters to help customize the response. For general information, see [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters).

| Name | Description |
| --- | --- |
| $select | Use the `$select` query parameter to return a set of properties that are different than the default set for an individual resource or a collection of resources. Only supported for **callRecord** and [session](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-session?view=graph-rest-1.0) resources. |
| $expand | Use the `$expand` query parameter to include the expanded resource or collection referenced by a single relationship ( **participants\_v2** or **sessions** and **segments**) in your results. For an example, see [Get session and segment details](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#example-2-get-session-and-segment-details). |

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Prefer: odata.maxpagesize={x} | Specifies a preferred integer {x} page size for paginated results. Optional. This value must be equal to or less than the maximum allowable page size. |
| Prefer: include-unknown-enum-members | Enables evolvable enum values beyond the sentinel value. For more information, see [Best Practices for working with Microsoft Graph](https://learn.microsoft.com/en-us/graph/best-practices-concept#handling-future-members-in-evolvable-enumerations). Optional. |
| Prefer: omit-values=nulls | Removes null or empty values from the response. Optional. |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a [microsoft.graph.callRecords.callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0) object in the response body. A request for a call record older than 30 days returns a `404 Not Found` response code.

When a result set spans multiple pages, Microsoft Graph returns that page with an **@odata.nextLink** property in the response that contains a URL to the next page of results. If that property is present, continue making additional requests with the **@odata.nextLink** URL in each response, until all the results are returned. For more information, see [Paging Microsoft Graph data in your app](https://learn.microsoft.com/en-us/graph/paging). Maximum page size: 130 entries for participants and 60 entries for sessions.

## Examples

### Example 1: Get basic details

The following example shows how to get the basic details from a [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0).

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/communications/callRecords/e523d2ed-2966-4b6b-925b-754a88034cc5
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Communications.CallRecords["{callRecord-id}"].GetAsync();
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
callRecords, err := graphClient.Communications().CallRecords().ByCallRecordId("callRecord-id").Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.callrecords.CallRecord result = graphClient.communications().callRecords().byCallRecordId("{callRecord-id}").get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let callRecord = await client.api('/communications/callRecords/e523d2ed-2966-4b6b-925b-754a88034cc5')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->communications()->callRecords()->byCallRecordId('callRecord-id')->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.CloudCommunications

Get-MgCommunicationCallRecord -CallRecordId $callRecordId
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.communications.call_records.by_call_record_id('callRecord-id').get()
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
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords/$entity",
  "version": 1,
  "type": "peerToPeer",
  "modalities": [\
    "audio"\
  ],
  "lastModifiedDateTime": "2020-02-25T19:00:24.582757Z",
  "startDateTime": "2020-02-25T18:52:21.2169889Z",
  "endDateTime": "2020-02-25T18:52:46.7640013Z",
  "id": "e523d2ed-2966-4b6b-925b-754a88034cc5",
  "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/organizer_v2/$entity",
  "organizer_v2": {
    "id": "821809f5-0000-0000-0000-3b5136c0e777",
    "identity": {
      "user": {
        "id": "821809f5-0000-0000-0000-3b5136c0e777",
        "displayName": "Abbie Wilkins",
        "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"
      }
    }
  },
  "participants_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/participants_v2/$entity"
}
```

### Example 2: Get session and segment details

The following example shows how to get the full session and segment details from a [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0).

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/communications/callRecords/e523d2ed-2966-4b6b-925b-754a88034cc5?$expand=sessions($expand=segments)
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Communications.CallRecords["{callRecord-id}"].GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Expand = new string []{ "sessions($expand=segments)" };
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

requestParameters := &graphcommunications.CallRecordsItemRequestBuilderGetQueryParameters{
	Expand: [] string {"sessions($expand=segments)"},
}
configuration := &graphcommunications.CallRecordsItemRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
callRecords, err := graphClient.Communications().CallRecords().ByCallRecordId("callRecord-id").Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.callrecords.CallRecord result = graphClient.communications().callRecords().byCallRecordId("{callRecord-id}").get(requestConfiguration -> {
	requestConfiguration.queryParameters.expand = new String []{"sessions($expand=segments)"};
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

let callRecord = await client.api('/communications/callRecords/e523d2ed-2966-4b6b-925b-754a88034cc5')
	.expand('sessions($expand=segments)')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Communications\CallRecords\Item\CallRecordItemRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new CallRecordItemRequestBuilderGetRequestConfiguration();
$queryParameters = CallRecordItemRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->expand = ["sessions(\$expand=segments)"];
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->communications()->callRecords()->byCallRecordId('callRecord-id')->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.CloudCommunications

Get-MgCommunicationCallRecord -CallRecordId $callRecordId -ExpandProperty "sessions(`$expand=segments)"
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.communications.call_records.item.call_record_item_request_builder import CallRecordItemRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = CallRecordItemRequestBuilder.CallRecordItemRequestBuilderGetQueryParameters(
		expand = ["sessions($expand=segments)"],
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.communications.call_records.by_call_record_id('callRecord-id').get(request_configuration = request_configuration)
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
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords(sessions(segments()))/$entity",
  "version": 1,
  "type": "peerToPeer",
  "modalities": [\
    "audio"\
  ],
  "lastModifiedDateTime": "2020-02-25T19:00:24.582757Z",
  "startDateTime": "2020-02-25T18:52:21.2169889Z",
  "endDateTime": "2020-02-25T18:52:46.7640013Z",
  "id": "e523d2ed-2966-4b6b-925b-754a88034cc5",
  "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/organizer_v2/$entity",
  "organizer_v2": {
    "id": "821809f5-0000-0000-0000-3b5136c0e777",
    "identity": {
      "user": {
        "id": "821809f5-0000-0000-0000-3b5136c0e777",
        "displayName": "Abbie Wilkins",
        "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"
      }
    }
  },
  "participants_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/participants_v2/$entity",
  "sessions": [\
    {\
      "modalities": [\
        "audio"\
      ],\
      "startDateTime": "2020-02-25T18:52:21.2169889Z",\
      "endDateTime": "2020-02-25T18:52:46.7640013Z",\
      "id": "e523d2ed-2966-4b6b-925b-754a88034cc5",\
      "isTest": false,\
      "caller": {\
        "@odata.type": "#microsoft.graph.callRecords.participantEndpoint",\
        "name": "machineName_2",\
        "userAgent": {\
          "@odata.type": "#microsoft.graph.callRecords.clientUserAgent",\
          "headerValue": "RTCC/7.0.0.0 UCWA/7.0.0.0 AndroidLync/6.25.0.27 (SM-G930U Android 8.0.0)",\
          "platform": "android",\
          "productFamily": "skypeForBusiness"\
        },\
        "associatedIdentity": {\
          "id": "821809f5-0000-0000-0000-3b5136c0e777",\
          "displayName": "Abbie Wilkins",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f",\
          "userPrincipalName": "abbie.wilkins@contoso.com"\
        }\
      },\
      "callee": {\
        "@odata.type": "#microsoft.graph.callRecords.participantEndpoint",\
        "name": "machineName_4",\
        "userAgent": {\
          "@odata.type": "#microsoft.graph.callRecords.clientUserAgent",\
          "headerValue": "UCCAPI/16.0.12527.20122 OC/16.0.12527.20194 (Skype for Business)",\
          "platform": "windows",\
          "productFamily": "skypeForBusiness"\
        },\
        "associatedIdentity": {\
          "id": "f69e2c00-0000-0000-0000-185e5f5f5d8a",\
          "displayName": "Owen Franklin",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f",\
          "userPrincipalName": "owen.franklin@contoso.com"\
        },\
        "feedback": {\
          "rating": "poor"\
        }\
      },\
      "segments": [\
        {\
          "startDateTime": "2020-02-25T18:52:21.2169889Z",\
          "endDateTime": "2020-02-25T18:52:46.7640013Z",\
          "id": "e523d2ed-2966-4b6b-925b-754a88034cc5",\
          "media": [\
            {\
              "label": "main-audio",\
              "callerNetwork": {\
                "ipAddress": "10.150.0.2",\
                "subnet": "10.150.0.0",\
                "linkSpeed": 54000000\
              },\
              "callerDevice": {\
                "captureDeviceName": "Default input device",\
                "renderDeviceName": "Default output device",\
                "receivedSignalLevel": -10\
              },\
              "streams": [\
                {\
                  "streamId": "1504545584",\
                  "streamDirection": "callerToCallee",\
                  "averageAudioDegradation": null,\
                  "averageJitter": "PT0.016S"\
                }\
              ]\
            }\
          ]\
        }\
      ]\
    }\
  ],
  "sessions@odata.nextLink": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/sessions?$expand=segments&$skiptoken=abc"
}
```

### Example 3: Get participant details

The following example shows how to expand the full paginated participant list for a [callRecord](https://learn.microsoft.com/en-us/graph/api/resources/callrecords-callrecord?view=graph-rest-1.0).

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/callrecords-callrecord-get?view=graph-rest-1.0&tabs=http#tabpanel_3_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/communications/callRecords/e523d2ed-2966-4b6b-925b-754a88034cc5?$expand=participants_v2
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Communications.CallRecords["{callRecord-id}"].GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Expand = new string []{ "participants_v2" };
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

requestParameters := &graphcommunications.CallRecordsItemRequestBuilderGetQueryParameters{
	Expand: [] string {"participants_v2"},
}
configuration := &graphcommunications.CallRecordsItemRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
callRecords, err := graphClient.Communications().CallRecords().ByCallRecordId("callRecord-id").Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.callrecords.CallRecord result = graphClient.communications().callRecords().byCallRecordId("{callRecord-id}").get(requestConfiguration -> {
	requestConfiguration.queryParameters.expand = new String []{"participants_v2"};
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

let callRecord = await client.api('/communications/callRecords/e523d2ed-2966-4b6b-925b-754a88034cc5')
	.expand('participants_v2')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Communications\CallRecords\Item\CallRecordItemRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new CallRecordItemRequestBuilderGetRequestConfiguration();
$queryParameters = CallRecordItemRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->expand = ["participants_v2"];
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->communications()->callRecords()->byCallRecordId('callRecord-id')->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.CloudCommunications

Get-MgCommunicationCallRecord -CallRecordId $callRecordId -ExpandProperty "participants_v2"
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.communications.call_records.item.call_record_item_request_builder import CallRecordItemRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = CallRecordItemRequestBuilder.CallRecordItemRequestBuilderGetQueryParameters(
		expand = ["participants_v2"],
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.communications.call_records.by_call_record_id('callRecord-id').get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

Copy

```
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords(participants_v2())/$entity",
  "version": 1,
  "type": "peerToPeer",
  "modalities": [\
    "audio"\
  ],
  "lastModifiedDateTime": "2020-02-25T19:00:24.582757Z",
  "startDateTime": "2020-02-25T18:52:21.2169889Z",
  "endDateTime": "2020-02-25T18:52:46.7640013Z",
  "id": "e523d2ed-2966-4b6b-925b-754a88034cc5",
  "organizer_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/organizer_v2/$entity",
  "organizer_v2": {
    "id": "821809f5-0000-0000-0000-3b5136c0e777",
    "identity": {
      "user": {
        "id": "821809f5-0000-0000-0000-3b5136c0e777",
        "displayName": "Abbie Wilkins",
        "tenantId": "dc368399-474c-4d40-900c-6265431fd81f"
      }
    }
  },
  "participants_v2@odata.context": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/participants_v2/$entity",
  "participants_v2@odata.nextLink": "https://graph.microsoft.com/v1.0/$metadata#communications/callRecords('e523d2ed-2966-4b6b-925b-754a88034cc5')/participants_v2?$skiptoken=abc",
  "participants_v2": [\
    {\
      "id": "821809f5-0000-0000-0000-3b5136c0e777",\
      "identity": {\
        "user": {\
          "id": "821809f5-0000-0000-0000-3b5136c0e777",\
          "displayName": "Abbie Wilkins",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f",\
          "userPrincipalName": "abbie.wilkins@contoso.com"\
        }\
      }\
    },\
    {\
      "id": "821809f5-0000-0000-0000-3b5136c0e777",\
      "identity": {\
        "user": {\
          "id": "f69e2c00-0000-0000-0000-185e5f5f5d8a",\
          "displayName": "Owen Franklin",\
          "tenantId": "dc368399-474c-4d40-900c-6265431fd81f",\
          "userPrincipalName": "owen.franklin@contoso.com"\
        }\
      }\
    }\
  ]
}
```

* * *
