# basicAuthentication resource type

Namespace: microsoft.graph

Represents configuration for using HTTP Basic authentication, which entails a username and password, in an API call. The username and password is sent as the Authorization header as `Basic {value}` where `value` is base 64 encoded version of username:password.

Inherits from [apiAuthenticationConfigurationBase](https://learn.microsoft.com/en-us/graph/api/resources/apiauthenticationconfigurationbase?view=graph-rest-1.0).

## Properties

| Property | Type | Description |
| --- | --- | --- |
| password | String | The password. It isn't returned in the responses. |
| username | String | The username. |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.basicAuthentication",
  "password": "String",
  "username": "String"
}
```

* * *
