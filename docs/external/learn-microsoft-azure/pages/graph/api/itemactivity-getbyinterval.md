# Get item activity stats by interval

Namespace: microsoft.graph

Important

APIs under the `/beta` version in Microsoft Graph are subject to change. Use of these APIs in production applications is not supported. To determine whether an API is available in v1.0, use the **Version** selector.

Get [itemActivityStats](https://learn.microsoft.com/en-us/graph/api/resources/itemactivitystat?view=graph-rest-beta) for the activities that took place under this resource within the specified time interval.

> **Note:** The **itemAnalytics** resource is not yet available in all [national deployments](https://learn.microsoft.com/en-us/graph/deployments).

Analytics aggregates might not be available for all action types.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Files.Read | Files.ReadWrite, Files.Read.All, Files.ReadWrite.All, Sites.Read.All, Sites.ReadWrite.All |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | Files.Read.All | Files.ReadWrite.All, Sites.Read.All, Sites.ReadWrite.All |

## HTTP request

HTTP

Copy

```http
GET /drives/{drive-id}/items/{item-id}/getActivitiesByInterval(startDateTime={startDateTime},endDateTime={endDateTime},interval={interval})
GET /sites/{site-id}/getActivitiesByInterval(startDateTime={startDateTime},endDateTime={endDateTime},interval={interval})
GET /sites/{site-id}/lists/{list-id}/items/{item-id}/getActivitiesByInterval(startDateTime={startDateTime},endDateTime={endDateTime},interval={interval})
```

## Function parameters

| Parameter | Type | Description |
| --- | --- | --- |
| startDateTime | string (timestamp) | The start time over which to aggregate activities. |
| endDateTime | string (timestamp) | The end time over which to aggregate activities. |
| interval | string | The aggregation interval. |

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and an [itemActivityStats](https://learn.microsoft.com/en-us/graph/api/resources/itemactivitystat?view=graph-rest-beta) object in the response body.

## Example

### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/itemactivity-getbyinterval?view=graph-rest-beta&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET /drives/{drive-id}/items/{item-id}/getActivitiesByInterval(startDateTime='2017-01-01',endDateTime='2017-01-3',interval='day')
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Drives["{drive-id}"].Items["{driveItem-id}"].GetActivitiesByIntervalWithStartDateTimeWithEndDateTimeWithInterval("{endDateTime}","{interval}","{startDateTime}").GetAsGetActivitiesByIntervalWithStartDateTimeWithEndDateTimeWithIntervalGetResponseAsync();
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v0.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-beta-sdk-go"
	  //other-imports
)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
startDateTime := "{startDateTime}"
endDateTime := "{endDateTime}"
interval := "{interval}"
getActivitiesByInterval, err := graphClient.Drives().ByDriveId("drive-id").Items().ByDriveItemId("driveItem-id").GetActivitiesByIntervalWithStartDateTimeWithEndDateTimeWithInterval(&startDateTime, &endDateTime, &interval).GetAsGetActivitiesByIntervalWithStartDateTimeWithEndDateTimeWithIntervalGetResponse(context.Background(), nil)
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

var result = graphClient.drives().byDriveId("{drive-id}").items().byDriveItemId("{driveItem-id}").getActivitiesByIntervalWithStartDateTimeWithEndDateTimeWithInterval("{endDateTime}", "{interval}", "{startDateTime}").get();
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let getActivitiesByInterval = await client.api('/drives/{drive-id}/items/{item-id}/getActivitiesByInterval(startDateTime='2017-01-01',endDateTime='2017-01-3',interval='day')')
	.version('beta')
	.get();
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\Beta\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->drives()->byDriveId('drive-id')->items()->byDriveItemId('driveItem-id')->getActivitiesByIntervalWithStartDateTimeWithEndDateTimeWithInterval('{endDateTime}', '{interval}', '{startDateTime}', )->get()->wait();
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Beta.Files

Get-MgBetaDriveItemActivityByInterval -DriveId $driveId -DriveItemId $driveItemId
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph_beta import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.drives.by_drive_id('drive-id').items.by_drive_item_id('driveItem-id').get_activities_by_interval_with_start_date_time_with_end_date_time_with_interval("{endDateTime}","{interval}","{startDateTime}").get()
```

Important

Microsoft Graph SDKs use the v1.0 version of the API by default, and do not support all the types, properties, and APIs available in the beta version. For details about accessing the beta API with the SDK, see [Use the Microsoft Graph SDKs with the beta API](https://learn.microsoft.com/en-us/graph/sdks/use-beta).

For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "value": [\
        {\
            "startDateTime": "2017-01-01T00:00:00.000Z",\
            "endDateTime": "2017-01-02T00:00:00.000Z",\
            "delete": {\
                "actionCount": 1,\
                "actorCount": 1\
            },\
            "access": {\
                "actionCount": 5,\
                "actorCount": 3\
            }\
        },\
        {\
            "startDateTime": "2017-01-02T00:00:00.000Z",\
            "endDateTime": "2017-01-03T00:00:00.000Z",\
            "edit": {\
                "actionCount": 3,\
                "actorCount": 1\
            },\
            "access": {\
                "actionCount": 7,\
                "actorCount": 6\
            }\
        }\
    ]
}
```

* * *
