# oidcClientSecretAuthentication resource type

Namespace: microsoft.graph

Important

APIs under the `/beta` version in Microsoft Graph are subject to change. Use of these APIs in production applications is not supported. To determine whether an API is available in v1.0, use the **Version** selector.

Represents client authentication information in an **oidcIdentityProvider** provider object where the client secret is used to authenticate the client application with the external OpenID Connect identity provider.

Inherits from [oidcClientAuthentication](https://learn.microsoft.com/en-us/graph/api/resources/oidcclientauthentication?view=graph-rest-beta).

## Properties

| Property | Type | Description |
| --- | --- | --- |
| clientSecret | String | The client secret obtained from configuring the client application on the external OpenID Connect identity provider. The property includes the client secret and enables the identity provider to use either the `client_secret_post` authentication method. |

### Where to get the client identifier and secret

Each identity provider has a process for creating an app registration. For example, users create an app registration with Facebook at [developers.facebook.com](https://developers.facebook.com/). The resulting client identifier and client secret can be passed to [create identityProvider](https://learn.microsoft.com/en-us/graph/api/identitycontainer-post-identityproviders?view=graph-rest-beta). Then, each user object in the directory can be federated to any of the tenant's identity providers for authentication. This enables the user to sign in by entering credentials on the identity provider's sign-in page. The token from the identity provider is validated by Microsoft Entra ID before the tenant issues a token to the application.

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.oidcClientSecretAuthentication",
  "clientSecret": "String"
}
```

* * *
