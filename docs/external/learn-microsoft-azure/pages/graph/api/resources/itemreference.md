# itemReference resource type

Namespace: microsoft.graph

The **itemReference** resource provides information necessary to address a [driveItem](https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0) or a [listItem](https://learn.microsoft.com/en-us/graph/api/resources/listitem?view=graph-rest-1.0) via the API.

## Properties

| Property | Type | Description |
| --- | --- | --- |
| driveId | String | Unique identifier of the drive instance that contains the driveItem. Only returned if the item is located in a [drive](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0). Read-only. |
| driveType | String | Identifies the type of drive. Only returned if the item is located in a [drive](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0). See [drive](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0) resource for values. |
| id | String | Unique identifier of the driveItem in the drive or a listItem in a list. Read-only. |
| name | String | The name of the item being referenced. Read-only. |
| path | String | Percent-encoded path that can be used to navigate to the item. Read-only. |
| shareId | String | A unique identifier for a shared resource that can be accessed via the [Shares](https://learn.microsoft.com/en-us/graph/api/shares-get?view=graph-rest-1.0) API. |
| sharepointIds | [sharepointIds](https://learn.microsoft.com/en-us/graph/api/resources/sharepointids?view=graph-rest-1.0) | Returns identifiers useful for SharePoint REST compatibility. Read-only. |
| siteId | String | For OneDrive for Business and SharePoint, this property represents the ID of the site that contains the parent document library of the driveItem resource or the parent list of the listItem resource. The value is the same as the id property of that [site](https://learn.microsoft.com/en-us/graph/api/resources/site?view=graph-rest-1.0) resource. It is an [opaque string that consists of three identifiers](https://learn.microsoft.com/en-us/graph/api/resources/site#id-property) of the site. <br>For OneDrive, this property is not populated. |

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "driveId": "string",
  "driveType": "personal | business | documentLibrary",
  "id": "string",
  "name": "string",
  "path": "string",
  "shareId": "string",
  "sharepointIds": { "@odata.type": "microsoft.graph.sharepointIds" },
  "siteId": "string"
}
```

## Remarks

To address a **driveItem** from an **itemReference** resource, construct a URL of the format:

HTTP

Copy

```http
GET https://graph.microsoft.com/v1.0/drives/{driveId}/items/{id}
```

The **path** value is a percent-encoded API path relative to the target drive, for example: `/drive/root:/Documents/my%20file.docx`.

To retrieve the human-readable path for a breadcrumb, you can safely ignore everything up to the first `:` in the path string.

* * *
