# List readingAssignmentSubmissions

Namespace: microsoft.graph

Get a list of [reading assignments](https://learn.microsoft.com/en-us/graph/api/resources/readingassignmentsubmission?view=graph-rest-1.0) that were submitted by a student.

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
| Application | EduReports-Reading.ReadAnonymous.All | EduReports-Reading.Read.All |

## HTTP request

HTTP

Copy

```http
GET /education/reports/readingAssignmentSubmissions
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

If successful, this method returns a `200 OK` response code and a collection of [readingAssignmentSubmission](https://learn.microsoft.com/en-us/graph/api/resources/readingassignmentsubmission?view=graph-rest-1.0) objects in the response body.

## Examples

### Example 1: Get a list of the reading assignment submissions from the last 24 hours

The following example shows how to get a list of the reading assignment submissions from the last 24 hours.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/education/reports/readingAssignmentSubmissions
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Education.Reports.ReadingAssignmentSubmissions.GetAsync();
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
readingAssignmentSubmissions, err := graphClient.Education().Reports().ReadingAssignmentSubmissions().Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ReadingAssignmentSubmissionCollectionResponse result = graphClient.education().reports().readingAssignmentSubmissions().get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let readingAssignmentSubmissions = await client.api('/education/reports/readingAssignmentSubmissions')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->education()->reports()->readingAssignmentSubmissions()->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Education

Get-MgEducationReportReadingAssignmentSubmission
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.education.reports.reading_assignment_submissions.get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the default response from the last 24 hours.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#education/reports/readingAssignmentSubmissions",
  "value": [\
    {\
      "action": "Attempt",\
      "assignmentId": "7622da88-d7fd-4542-a62b-40e11304675e",\
      "classId": "d208c32d-6d82-442f-bedd-d730d0d2a539",\
      "submissionId": "22142311-f797-90ec-997e-a8b16d3d4479",\
      "studentId": "392d15be-6e42-4e50-babf-56103abfc525",\
      "submissionDateTime": "2025-06-16T23:56:17.1505334Z",\
      "accuracyScore": 25.0,\
      "wordsPerMinute": 135.0,\
      "wordCount": 138,\
      "mispronunciations": 1,\
      "omissions": 99,\
      "insertions": 3,\
      "selfCorrections": 0,\
      "repetitions": 0,\
      "monotoneScore": 100.0,\
      "missedShorts": 0,\
      "missedExclamationMarks": 1,\
      "missedPeriods": 1,\
      "missedQuestionMarks": 0,\
      "unexpectedPauses": 1,\
      "challengingWords": [\
        {\
          "word": "many",\
          "count": 1\
        }\
      ]\
    },\
    {\
      "action": "Attempt",\
      "assignmentId": "7622da88-d7fd-4542-a62b-40e11304675e",\
      "classId": "d208c32d-6d82-442f-bedd-d730d0d2a539",\
      "submissionId": "22142311-f797-90ec-997e-a8b16d3d4479",\
      "studentId": "392d15be-6e42-4e50-babf-56103abfc525",\
      "submissionDateTime": "2025-06-16T23:54:22.6784676Z",\
      "accuracyScore": 36.0,\
      "wordsPerMinute": 190.0,\
      "wordCount": 94,\
      "mispronunciations": 6,\
      "omissions": 54,\
      "insertions": 0,\
      "selfCorrections": 0,\
      "repetitions": 0,\
      "monotoneScore": 100.0,\
      "missedShorts": 0,\
      "missedExclamationMarks": 0,\
      "missedPeriods": 5,\
      "missedQuestionMarks": 0,\
      "unexpectedPauses": 0,\
      "challengingWords": [\
        {\
          "word": "polar",\
          "count": 1\
        },\
        {\
          "word": "bears",\
          "count": 1\
        },\
        {\
          "word": "snow",\
          "count": 1\
        },\
        {\
          "word": "closed",\
          "count": 1\
        },\
        {\
          "word": "drinks",\
          "count": 1\
        },\
        {\
          "word": "milk",\
          "count": 1\
        }\
      ]\
    }\
  ]
}
```

### Example 2: Get a list of the reading assignment submissions for a specific date using $filter

The following example shows how to get a list of the reading assignment submissions for a specific date using the `$filter` query parameter. The requested time range must be 24 hours or shorter.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/reportsroot-list-readingassignmentsubmissions?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/education/reports/readingAssignmentSubmissions?$filter=submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Education.Reports.ReadingAssignmentSubmissions.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z";
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

requestFilter := "submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z"

requestParameters := &grapheducation.ReportsReadingAssignmentSubmissionsRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
}
configuration := &grapheducation.ReportsReadingAssignmentSubmissionsRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
readingAssignmentSubmissions, err := graphClient.Education().Reports().ReadingAssignmentSubmissions().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ReadingAssignmentSubmissionCollectionResponse result = graphClient.education().reports().readingAssignmentSubmissions().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z";
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

let readingAssignmentSubmissions = await client.api('/education/reports/readingAssignmentSubmissions')
	.filter('submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Education\Reports\ReadingAssignmentSubmissions\ReadingAssignmentSubmissionsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ReadingAssignmentSubmissionsRequestBuilderGetRequestConfiguration();
$queryParameters = ReadingAssignmentSubmissionsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->education()->reports()->readingAssignmentSubmissions()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Education

Get-MgEducationReportReadingAssignmentSubmission -Filter "submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z"
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.education.reports.reading_assignment_submissions.reading_assignment_submissions_request_builder import ReadingAssignmentSubmissionsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ReadingAssignmentSubmissionsRequestBuilder.ReadingAssignmentSubmissionsRequestBuilderGetQueryParameters(
		filter = "submissionDateTime gt 2025-06-10T00:00:00.000Z and submissionDateTime lt 2025-06-11T00:00:00Z",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.education.reports.reading_assignment_submissions.get(request_configuration = request_configuration)
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
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#education/reports/readingAssignmentSubmissions",
  "value": [\
    {\
      "action": "Attempt",\
      "assignmentId": "f45e1c35-81fd-48b0-b214-1216d6b42203",\
      "classId": "dd1324ff-93f7-4e57-8bd4-355f180cd8f1",\
      "submissionId": "2e8f9537-75e1-bf0c-83dd-a2c3de140aa4",\
      "studentId": "225031f2-88ae-4566-b636-6a032dfbed4c",\
      "submissionDateTime": "2025-06-10T21:43:21.9472942Z",\
      "accuracyScore": 38.0,\
      "wordsPerMinute": 135.0,\
      "wordCount": 94,\
      "mispronunciations": 3,\
      "omissions": 55,\
      "insertions": 0,\
      "selfCorrections": 0,\
      "repetitions": 0,\
      "monotoneScore": 0.0,\
      "missedShorts": 0,\
      "missedExclamationMarks": 0,\
      "missedPeriods": 4,\
      "missedQuestionMarks": 0,\
      "unexpectedPauses": 0,\
      "challengingWords": [\
        {\
          "word": "bears",\
          "count": 1\
        },\
        {\
          "word": "eyes",\
          "count": 1\
        },\
        {\
          "word": "closed",\
          "count": 1\
        }\
      ]\
    },\
    {\
      "action": "Attempt",\
      "assignmentId": "57717841-1965-4ff3-9601-b0366e583069",\
      "classId": "b609d225-c661-4562-933a-e23679175f0b",\
      "submissionId": "ca42757d-7914-afe2-b044-f9695694b39b",\
      "studentId": "392d15be-6e42-4e50-babf-56103abfc525",\
      "submissionDateTime": "2025-06-10T20:21:39.4111647Z",\
      "accuracyScore": 0.0,\
      "wordsPerMinute": 0.0,\
      "wordCount": 150,\
      "mispronunciations": 0,\
      "omissions": 150,\
      "insertions": 0,\
      "selfCorrections": 0,\
      "repetitions": 0,\
      "monotoneScore": 0.0,\
      "missedShorts": 0,\
      "missedExclamationMarks": 0,\
      "missedPeriods": 0,\
      "missedQuestionMarks": 0,\
      "unexpectedPauses": 0,\
      "challengingWords": []\
    },\
    {\
      "action": "EditMiscue",\
      "assignmentId": "c5c08b85-35fa-48d6-99bb-2168e53fd041",\
      "classId": "d208c32d-6d82-442f-bedd-d730d0d2a539",\
      "submissionId": "3ef9af57-20f1-d7c5-3705-8ec80db3121c",\
      "studentId": "392d15be-6e42-4e50-babf-56103abfc525",\
      "submissionDateTime": "2025-06-10T20:10:09.4739427Z",\
      "accuracyScore": 0.0,\
      "wordsPerMinute": 0.0,\
      "wordCount": 384,\
      "mispronunciations": 0,\
      "omissions": 383,\
      "insertions": 1,\
      "selfCorrections": 0,\
      "repetitions": 0,\
      "monotoneScore": 0.0,\
      "missedShorts": 0,\
      "missedExclamationMarks": 0,\
      "missedPeriods": 0,\
      "missedQuestionMarks": 0,\
      "unexpectedPauses": 0,\
      "challengingWords": []\
    }\
  ]
}
```

* * *
