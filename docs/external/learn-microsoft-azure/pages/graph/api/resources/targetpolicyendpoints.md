# targetPolicyEndpoints resource type

Namespace: microsoft.graph

Important

APIs under the `/beta` version in Microsoft Graph are subject to change. Use of these APIs in production applications is not supported. To determine whether an API is available in v1.0, use the **Version** selector.

Represents the platforms that can be targeted to receive notifications sent to the user. These include Windows, iOS, Android and Web.

## Properties

| Property | Type | Description |
| --- | --- | --- |
| platformTypes | String collection | Use to filter the notification distribution to a specific platform or platforms. Valid values are `Windows`, `iOS`, `Android` and `WebPush`. By default, all push endpoint types (Windows, iOS, Android and WebPush) are enabled. |

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "platformTypes": ["String"]
}
```

* * *
