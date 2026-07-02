# List reflectCheckInResponses

Namespace: microsoft.graph

Get a list of [Reflect check-ins](https://learn.microsoft.com/en-us/graph/api/resources/reflectcheckinresponse?view=graph-rest-1.0) that were submitted by a student.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ❌ | ❌ | ❌ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Not supported. | Not supported. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | EduReports-Reflect.ReadAnonymous.All | EduReports-Reflect.Read.All |

## HTTP request

HTTP

Copy

```http
GET /education/reports/reflectCheckInResponses
```

## Optional query parameters

This method supports the `$top`, `$filter`, `$count`, `$skiptoken` and `$select` OData query parameters to help customize the response. For general information, see [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters).

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a collection of [reflectCheckInResponse](https://learn.microsoft.com/en-us/graph/api/resources/reflectcheckinresponse?view=graph-rest-1.0) objects in the response body.

## Examples

### Example 1: Get a list of the Reflect check-in responses from the last 24 hours

The following example shows how to get a list of the Reflect check-in responses from the last 24 hours.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/education/reports/reflectCheckInResponses
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Education.Reports.ReflectCheckInResponses.GetAsync();
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
reflectCheckInResponses, err := graphClient.Education().Reports().ReflectCheckInResponses().Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ReflectCheckInResponseCollectionResponse result = graphClient.education().reports().reflectCheckInResponses().get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let reflectCheckInResponses = await client.api('/education/reports/reflectCheckInResponses')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->education()->reports()->reflectCheckInResponses()->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Education

Get-MgEducationReportReflectCheck
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.education.reports.reflect_check_in_responses.get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the default response that includes Reflect check-in responses from the last 24 hours.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "@odata.context": "https://canary.graph.microsoft.com/v1.0/$metadata#education/reports/reflectCheckInResponses",
  "value": [\
    {\
      "checkInId": "39878fe8-cb41-3feb-c547-90b37160ceb6",\
      "creatorId": "52115927-a289-4a3b-9b8c-95049ee3f7c3",\
      "classId": "56fb315f-129d-4ad3-90fd-99398f9eb922",\
      "checkInTitle": "How are you feeling today?",\
      "isClosed": true,\
      "createdDateTime": "2025-06-17T16:53:03Z",\
      "responderId": "e3030ce4-d660-434a-b569-071402d751b5",\
      "responseFeedback": "neutral",\
      "responseEmotion": "none",\
      "submitDateTime": "2025-06-17T16:53:50.3020719Z"\
    },\
    {\
      "checkInId": "2cbcf1f4-d8e2-f9d3-6ce7-ec92caa792bd",\
      "creatorId": "3b1bb03f-f52b-4d21-8f60-69ba571aaa61",\
      "classId": "f92cf95c-2a24-4dab-8ced-89521a1e4ce0",\
      "checkInTitle": "How are you feeling today?",\
      "isClosed": true,\
      "createdDateTime": "2025-06-17T16:50:53Z",\
      "responderId": "e3030ce4-d660-434a-b569-071402d751b5",\
      "responseFeedback": "neutral",\
      "responseEmotion": "none",\
      "submitDateTime": "2025-06-17T16:51:17.8334267Z"\
    }\
  ]
}
```

### Example 2: Get a list of the Reflect check-in responses for a specific date using $filter

The following example shows how to get a list of the Reflect check-in responses for a specific date using the `$filter` query parameter. The requested time range must be 24 hours or shorter.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-reflectcheckinresponses?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/education/reports/reflectCheckInResponses?$filter=submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Education.Reports.ReflectCheckInResponses.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z";
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
	  grapheducation "github.com/microsoftgraph/msgraph-sdk-go/education"
	  //other-imports
)

requestFilter := "submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z"

requestParameters := &grapheducation.ReportsReflectCheckInResponsesRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
}
configuration := &grapheducation.ReportsReflectCheckInResponsesRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
reflectCheckInResponses, err := graphClient.Education().Reports().ReflectCheckInResponses().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ReflectCheckInResponseCollectionResponse result = graphClient.education().reports().reflectCheckInResponses().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z";
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

let reflectCheckInResponses = await client.api('/education/reports/reflectCheckInResponses')
	.filter('submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Education\Reports\ReflectCheckInResponses\ReflectCheckInResponsesRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ReflectCheckInResponsesRequestBuilderGetRequestConfiguration();
$queryParameters = ReflectCheckInResponsesRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->education()->reports()->reflectCheckInResponses()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Education

Get-MgEducationReportReflectCheck -Filter "submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z"
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.education.reports.reflect_check_in_responses.reflect_check_in_responses_request_builder import ReflectCheckInResponsesRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ReflectCheckInResponsesRequestBuilder.ReflectCheckInResponsesRequestBuilderGetQueryParameters(
		filter = "submitDateTime gt 2025-06-11T00:00:00.000Z and submitDateTime lt 2025-06-12T00:00:00Z",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.education.reports.reflect_check_in_responses.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "@odata.context": "https://canary.graph.microsoft.com/v1.0/$metadata#education/reports/reflectCheckInResponses",
  "value": [\
    {\
      "checkInId": "b815ab15-7a52-1cf7-898d-9a018cfb3369",\
      "creatorId": "df8123ca-5226-4227-8bc1-94b753fab5a4",\
      "classId": "a03ed51d-a5a2-4b5d-9b8b-21bae3fff05c",\
      "checkInTitle": "How are you feeling today?",\
      "isClosed": true,\
      "createdDateTime": "2025-06-11T16:58:18Z",\
      "responderId": "a9db035b-f866-4c80-9608-d3364ae8c479",\
      "responseFeedback": "unpleasant",\
      "responseEmotion": "none",\
      "submitDateTime": "2025-06-11T17:04:29.0427967Z"\
    },\
    {\
      "checkInId": "b815ab15-7a52-1cf7-898d-9a018cfb3369",\
      "creatorId": "df8123ca-5226-4227-8bc1-94b753fab5a4",\
      "classId": "a03ed51d-a5a2-4b5d-9b8b-21bae3fff05c",\
      "checkInTitle": "How are you feeling today?",\
      "isClosed": true,\
      "createdDateTime": "2025-06-11T16:58:18Z",\
      "responderId": "9856811e-2e4d-42bd-a1e7-58d52155de23",\
      "responseFeedback": "pleasant",\
      "responseEmotion": "none",\
      "submitDateTime": "2025-06-11T17:00:47.7001549Z"\
    }\
  ]
}
```

* * *
