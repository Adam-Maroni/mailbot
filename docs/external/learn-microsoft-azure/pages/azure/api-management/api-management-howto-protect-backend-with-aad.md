# Protect an API in Azure API Management using OAuth 2.0 authorization with Microsoft Entra ID

**APPLIES TO: All API Management tiers**

In this article, you learn high level steps to configure your [Azure API Management](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts) instance to protect an API, by using the [OAuth 2.0 protocol with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/active-directory/develop/active-directory-v2-protocols).

For a conceptual overview of API authorization, see [Authentication and authorization to APIs in API Management](https://learn.microsoft.com/en-us/azure/api-management/authentication-authorization-overview).

## Prerequisites

Before following the steps in this article, you must have:

- An API Management instance
- A published API using the API Management instance
- A Microsoft Entra tenant

## Overview

Follow these steps to protect an API in API Management, using OAuth 2.0 authorization with Microsoft Entra ID.

1. Register an application (called _backend-app_ in this article) in Microsoft Entra ID.

To access the API, users or applications must acquire and present a valid OAuth token granting access to this application with each API request.

2. Configure the [validate-jwt](https://learn.microsoft.com/en-us/azure/api-management/validate-jwt-policy) policy in API Management. This policy validates the OAuth token presented in each incoming API request. Valid requests can be passed to the API.

Details about OAuth authorization flows and how to generate the required OAuth tokens are beyond the scope of this article. Typically, a separate client app is used to acquire tokens from Microsoft Entra ID that authorize access to the API. For links to more information, see the [related content](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-protect-backend-with-aad#related-content) section.

## Register an application in Microsoft Entra ID to represent the API

Using the Azure portal, protect an API with Microsoft Entra ID by first registering an application that represents the API.

For details about app registration, see [Quickstart: Configure an application to expose a web API](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-configure-app-expose-web-apis).

01. In the [Azure portal](https://portal.azure.com/), search for and select **App registrations**.

02. Select **New registration**.

03. When the **Register an application page** appears, enter your application's registration information:

    - In the **Name** section, enter a meaningful application name, such as _backend-app_. This name is displayed to users of the app.
    - In the **Supported account types** section, select an option that suits your scenario.
04. Leave the [**Redirect URI**](https://learn.microsoft.com/en-us/azure/active-directory/develop/reply-url) section empty.

05. Select **Register** to create the application.

06. On the app **Overview** page, find the **Application (client) ID** value and record it for later.

07. Under the **Manage** section of the side menu, select **Expose an API** and set the **Application ID URI** with the default value. If you're developing a separate client app to obtain OAuth 2.0 tokens for access to the backend-app, record this value for later.

08. Select the **Add a scope** button to display the **Add a scope** page:

    1. Enter a new **Scope name**, **Admin consent display name**, and **Admin consent description**.
    2. Make sure the **Enabled** scope state is selected.
09. Select the **Add scope** button to create the scope.

10. Repeat the previous two steps to add all scopes supported by your API.

11. Once the scopes are created, make a note of them for use later.

## Configure a JWT validation policy to pre-authorize requests

The following example policy, when added to the `<inbound>` policy section, checks the value of the audience claim in an access token obtained from Microsoft Entra ID that is presented in the Authorization header. It returns an error message if the token is not valid. Configure this policy at a policy scope that's appropriate for your scenario.

- In the `openid-config` URL, the `aad-tenant` is the tenant ID in Microsoft Entra ID. Find this value in the Azure portal, for example, on the **Overview** page of your Microsoft Entra resource. The example shown assumes a single-tenant Microsoft Entra app and a v2 configuration endpoint.
- The value of the `claim` is the client ID of the backend-app you registered in Microsoft Entra ID.

XML

Copy

```xml
<validate-jwt header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized. Access token is missing or invalid.">
    <openid-config url="https://login.microsoftonline.com/{aad-tenant}/v2.0/.well-known/openid-configuration" />
    <audiences>
        <audience>{audience-value - (ex:api://guid)}</audience>
    </audiences>
    <issuers>
        <issuer>{issuer-value - (ex: https://sts.windows.net/{tenant id}/)}</issuer>
    </issuers>
    <required-claims>
        <claim name="aud">
            <value>{backend-app-client-id}</value>
        </claim>
    </required-claims>
</validate-jwt>
```

The preceding `openid-config` URL corresponds to the v2 endpoint. For the v1 `openid-config` endpoint, use `https://login.microsoftonline.com/{aad-tenant}/.well-known/openid-configuration`.

For information on how to configure policies, see [Set or edit policies](https://learn.microsoft.com/en-us/azure/api-management/set-edit-policies). Refer to the [validate-jwt](https://learn.microsoft.com/en-us/azure/api-management/validate-jwt-policy) reference for more customization on JWT validations. To validate a JWT that was provided by the Microsoft Entra service, API Management also provides the [`validate-azure-ad-token`](https://learn.microsoft.com/en-us/azure/api-management/validate-azure-ad-token-policy) policy.

## Authorization workflow

1. A user or application acquires a token from Microsoft Entra ID with permissions that grant access to the backend-app. If you use the v2 endpoint, ensure that the `accessTokenAcceptedVersion` property is set to `2` in the application manifest of the backend app and any client app that you configure.

2. The token is added in the Authorization header of API requests to API Management.

3. API Management validates the token by using the `validate-jwt` policy.

   - If a request doesn't have a valid token, API Management blocks it.

   - If a request does have a valid token, the gateway can forward the request to the API.

## Related content

- To learn more about how to build an application and implement OAuth 2.0, see [Microsoft Entra code samples](https://learn.microsoft.com/en-us/azure/active-directory/develop/sample-v2-code).

- For an end-to-end example of configuring OAuth 2.0 user authorization in the API Management developer portal, see [How to authorize test console of developer portal by configuring OAuth 2.0 user authorization](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-oauth2).

- Learn more about [Microsoft Entra ID and OAuth2.0](https://learn.microsoft.com/en-us/azure/active-directory/develop/authentication-vs-authorization).

- For other ways to secure your back-end service, see [Mutual certificate authentication](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-mutual-certificates).

* * *
