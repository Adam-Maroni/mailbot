# cloudPcSnapshotImportActionResult resource type

Namespace: microsoft.graph

Important

APIs under the `/beta` version in Microsoft Graph are subject to change. Use of these APIs in production applications is not supported. To determine whether an API is available in v1.0, use the **Version** selector.

Represents the result of the [snapshot](https://learn.microsoft.com/en-us/graph/api/resources/cloudpcsnapshot?view=graph-rest-beta) import action. Each action has a status and can be tracked individually. When the action returns a succeeded status, the snapshot is ready for use in Cloud PC provisioning.

Windows 365 administrators must prepare a provisioning policy and assign it to users as a requirement for snapshot import.

## Properties

| Property | Type | Description |
| --- | --- | --- |
| additionalDetail | String | More details about the snapshot import action. For example, `The snapshot import has failed because the file format is incorrect`. This property only contains a value when errors occur during the process. Read-only. |
| assignedUserPrincipalName | String | The assigned user's principal name. For example, `ryan@contoso.com`. |
| endDateTime | DateTimeOffset | The end time of the snapshot import action. The timestamp is shown in ISO 8601 format and Coordinated Universal Time (UTC). For example, midnight UTC on Jan 1, 2014 appear as `2014-01-01T00:00:00Z`. Read-only. |
| filename | String | The file name for the imported snapshot. For example: `MyCloudPc.vhd`. Read-only. |
| importStatus | [cloudPcSnapshotImportActionStatus](https://learn.microsoft.com/en-us/graph/api/resources/cloudpcsnapshotimportactionresult?view=graph-rest-beta#cloudpcsnapshotimportactionstatus-values) | The status of the snapshot import action. The possible values are: `pending`, `inProgress`, `succeeded`, `failed`, `unknownFutureValue`. The default value is `pending`. Read-only. |
| policyName | String | The name of the assigned provisioning policy for the upload action. This policy takes effect if a new Cloud PC is provisioned. For example, `MyProvisioningPolicy`. Read-only. |
| snapshotId | String | The unique identifier for the imported snapshot. For example, `d09ae73d-b70f-4836-95c1-59652c947e1c`. Read-only. |
| startDateTime | DateTimeOffset | The start time of the snapshot import action. The timestamp is shown in ISO 8601 format and Coordinated Universal Time (UTC). For example, midnight UTC on Jan 1, 2014 appear as `2014-01-01T00:00:00Z`. Read-only. |
| usageStatus | [cloudPcImportedSnapshotState](https://learn.microsoft.com/en-us/graph/api/resources/cloudpcsnapshotimportactionresult?view=graph-rest-beta#cloudpcimportedsnapshotstate-values) | The Cloud PC usage status of the imported snapshot. The possible values are: `notUsed`, `inUse`, `expired`, `unknownFutureValue`. The default value is `notUsed`. Read-only. |

### cloudPcImportedSnapshotState values

| Member | Description |
| --- | --- |
| notUsed | Indicates that the snapshot isn't yet used. |
| inUse | Indicates that the snapshot is currently in use. |
| expired | Indicates that the snapshot is expired and can no longer be used. |
| unknownFutureValue | Evolvable enumeration sentinel value. Don't use. |

### cloudPcSnapshotImportActionStatus values

| Member | Description |
| --- | --- |
| pending | Indicates that the snapshot upload is queued and yet to start. |
| inProgress | Indicates that the snapshot upload is in progress. |
| succeeded | Indicates that the snapshot upload action finished successfully. |
| failed | Indicates that the snapshot upload failed. |
| unknownFutureValue | Evolvable enumeration sentinel value. Don't use. |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.cloudPcSnapshotImportActionResult",
  "additionalDetail": "String",
  "assignedUserPrincipalName": "String",
  "endDateTime": "String (timestamp)",
  "filename": "String",
  "importStatus": "String",
  "policyName": "String",
  "snapshotId": "String",
  "startDateTime": "String (timestamp)",
  "usageStatus": "String"
}
```

* * *
