# List transcripts

Namespace: microsoft.graph

Retrieve the list of [callTranscript](https://learn.microsoft.com/en-us/graph/api/resources/calltranscript?view=graph-rest-1.0) objects associated with a scheduled [onlineMeeting](https://learn.microsoft.com/en-us/graph/api/resources/onlinemeeting?view=graph-rest-1.0). This API supports the retrieval of call transcripts from all meeting types except live events.

- This API doesn't support meetings created using the [create onlineMeeting API](https://learn.microsoft.com/en-us/graph/api/application-post-onlinemeetings) that are not associated with an event on the user's calendar.
- This API works differently in one or more national clouds. For details, see [Microsoft Teams API implementation differences in national clouds](https://learn.microsoft.com/en-us/graph/teamwork-national-cloud-differences).

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ❌ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | OnlineMeetingTranscript.Read.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | OnlineMeetingTranscript.Read.All, OnlineMeetingTranscript.Read.Chat | Not available. |

The application permissions `OnlineMeetingTranscript.Read.Chat` uses [resource-specific consent](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent). The `OnlineMeetingTranscript.Read.Chat` permission applies only to scheduled private chat meetings, not to channel meetings.

To use application permissions for this API, tenant administrators must create an application access policy and grant it to a user. It authorizes the app configured in the policy to fetch online meetings or online meeting artifacts on behalf of that user (with the user ID specified in the request path). For more information, see [Allow applications to access online meetings on behalf of a user](https://learn.microsoft.com/en-us/graph/cloud-communication-online-meeting-application-access-policy).

This API works for a meeting only if the meeting has not expired. For more information, see [Limits and specifications for Microsoft Teams](https://learn.microsoft.com/en-us/microsoftteams/limits-specifications-teams#meeting-expiration).

## HTTP request

HTTP

Copy

```http
GET /me/onlineMeetings/{online-meeting-id}/transcripts
GET /users/{user-id}/onlineMeetings/{online-meeting-id}/transcripts
```

## Optional query parameters

This method supports the `$select`, `$filter`, and `$top` [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters) to customize the response.

## Request headers

| Header | Value |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a collection of [callTranscript](https://learn.microsoft.com/en-us/graph/api/resources/calltranscript?view=graph-rest-1.0) objects in the response body.

## Examples

### Request

The following examples show a request and its response.

For online meetings

- [HTTP](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/users/ba321e0d-79ee-478d-8e28-85a19507f456/onlineMeetings/MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ/transcripts
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Users["{user-id}"].OnlineMeetings["{onlineMeeting-id}"].Transcripts.GetAsync();
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
transcripts, err := graphClient.Users().ByUserId("user-id").OnlineMeetings().ByOnlineMeetingId("onlineMeeting-id").Transcripts().Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

CallTranscriptCollectionResponse result = graphClient.users().byUserId("{user-id}").onlineMeetings().byOnlineMeetingId("{onlineMeeting-id}").transcripts().get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let transcripts = await client.api('/users/ba321e0d-79ee-478d-8e28-85a19507f456/onlineMeetings/MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ/transcripts')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->users()->byUserId('user-id')->onlineMeetings()->byOnlineMeetingId('onlineMeeting-id')->transcripts()->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.CloudCommunications

Get-MgUserOnlineMeetingTranscript -UserId $userId -OnlineMeetingId $onlineMeetingId
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.users.by_user_id('user-id').online_meetings.by_online_meeting_id('onlineMeeting-id').transcripts.get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

The following example shows the response.

The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('ba321e0d-79ee-478d-8e28-85a19507f456')/onlineMeetings('MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ')/transcripts",
    "@odata.count": 3,
    "value": [\
        {\
            "id": "MSMjMCMjZDAwYWU3NjUtNmM2Yi00NjQxLTgwMWQtMTkzMmFmMjEzNzdh",\
            "meetingId": "MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ",\
            "callId": "af630fe0-04d3-4559-8cf9-91fe45e36296",\
            "createdDateTime": "2021-09-17T06:09:24.8968037Z",\
            "endDateTime": "2023-04-10T08:27:25.2346000Z",\
            "contentCorrelationId": "bc842d7a-2f6e-4b18-a1c7-73ef91d5c8e3",\
            "transcriptContentUrl": "https://graph.microsoft.com/v1.0/$metadata#users('ba321e0d-79ee-478d-8e28-85a19507f456')/onlineMeetings('MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ')/transcripts/('MSMjMCMjZDAwYWU3NjUtNmM2Yi00NjQxLTgwMWQtMTkzMmFmMjEzNzdh')/content",\
            "meetingOrganizer": {\
                "application": null,\
                "device": null,\
                "user": {\
                    "@odata.type": "#Microsoft.Teams.GraphSvc.teamworkUserIdentity",\
                    "id": "ba321e0d-79ee-478d-8e28-85a19507f456",\
                    "displayName": null,\
                    "userIdentityType": "aadUser",\
                    "tenantId": "cd6cee19-2d76-4ee0-8f47-9ed12ee44331"\
                }\
            }\
        },\
        {\
            "id": "MSMjMCMjMzAxNjNhYTctNWRmZi00MjM3LTg5MGQtNWJhYWZjZTZhNWYw",\
            "meetingId": "MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ",\
            "callId": "af630fe0-04d3-4559-8cf9-91fe45e36296",\
            "createdDateTime": "2021-09-16T18:58:58.6760692Z",\
            "endDateTime": "2023-04-10T08:27:25.2346000Z",\
            "contentCorrelationId": "bc842d7a-2f6e-4b18-a1c7-73ef91d5c8e3",\
            "transcriptContentUrl": "https://graph.microsoft.com/v1.0/$metadata#users('ba321e0d-79ee-478d-8e28-85a19507f456')/onlineMeetings('MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ')/transcripts/('MSMjMCMjMzAxNjNhYTctNWRmZi00MjM3LTg5MGQtNWJhYWZjZTZhNWYw')/content",\
            "meetingOrganizer": {\
                "application": null,\
                "device": null,\
                "user": {\
                    "@odata.type": "#Microsoft.Teams.GraphSvc.teamworkUserIdentity",\
                    "id": "ba321e0d-79ee-478d-8e28-85a19507f456",\
                    "displayName": null,\
                    "userIdentityType": "aadUser",\
                    "tenantId": "cd6cee19-2d76-4ee0-8f47-9ed12ee44331"\
                }\
            }\
        },\
        {\
            "id": "MSMjMCMjNzU3ODc2ZDYtOTcwMi00MDhkLWFkNDItOTE2ZDNmZjkwZGY4",\
            "meetingId": "MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ",\
            "callId": "af630fe0-04d3-4559-8cf9-91fe45e36296",\
            "createdDateTime": "2021-09-16T18:56:00.9038309Z",\
            "endDateTime": "2023-04-10T08:27:25.2346000Z",\
            "contentCorrelationId": "bc842d7a-2f6e-4b18-a1c7-73ef91d5c8e3",\
            "transcriptContentUrl": "https://graph.microsoft.com/v1.0/$metadata#users('ba321e0d-79ee-478d-8e28-85a19507f456')/onlineMeetings('MSo1N2Y5ZGFjYy03MWJmLTQ3NDMtYjQxMy01M2EdFGkdRWHJlQ')/transcripts/('MSMjMCMjNzU3ODc2ZDYtOTcwMi00MDhkLWFkNDItOTE2ZDNmZjkwZGY4')/content",\
            "meetingOrganizer": {\
                "application": null,\
                "device": null,\
                "user": {\
                    "@odata.type": "#Microsoft.Teams.GraphSvc.teamworkUserIdentity",\
                    "id": "ba321e0d-79ee-478d-8e28-85a19507f456",\
                    "displayName": null,\
                    "userIdentityType": "aadUser",\
                    "tenantId": "cd6cee19-2d76-4ee0-8f47-9ed12ee44331"\
                }\
            }\
        }\
    ]
}
```

* * *
