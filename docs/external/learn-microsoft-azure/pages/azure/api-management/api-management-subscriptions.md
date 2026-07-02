# Subscriptions in Azure API Management

**APPLIES TO: All API Management tiers**

In Azure API Management, _subscriptions_ are the most common way for API consumers to access APIs published through an API Management instance. This article provides an overview of the concept.

An API Management subscription is used specifically to call APIs through API Management by using a subscription key. It's not the same as an Azure subscription.

## What are subscriptions?

By publishing APIs through API Management, you can easily secure API access by using subscription keys. Developers who need to consume the published APIs must include a valid subscription key in HTTP requests when calling those APIs. Without a valid subscription key, the calls are:

- Rejected immediately by the API Management gateway.
- Not forwarded to the back-end services.

To access APIs, developers need a subscription and a subscription key. A _subscription_ is a named container for a pair of subscription keys.

In addition,

- Developers can get subscriptions without needing approval from API publishers.
- API publishers can create subscriptions directly for API consumers.

Tip

API Management also supports other mechanisms for securing access to APIs, including the following examples:

- [OAuth2.0](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-protect-backend-with-aad)
- [Client certificates](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-mutual-certificates-for-clients)
- [Restrict caller IPs](https://learn.microsoft.com/en-us/azure/api-management/ip-filter-policy)

## Manage subscription keys

Regularly regenerating keys is a common security precaution. Like most Azure services that require a subscription key, API Management generates keys in pairs. Each application that uses the service can switch from _key A_ to _key B_ and regenerate key A with minimal disruption, and vice versa.

Instead of regenerating keys, you can set specific keys by invoking the [Azure API Management Subscription - Create Or Update Azure REST API](https://learn.microsoft.com/en-us/rest/api/apimanagement/current-ga/subscription/create-or-update). Specifically, set `properties.primaryKey` and/or `properties.secondaryKey` in the HTTP request body.

- API Management doesn't provide built-in features to manage the lifecycle of subscription keys, such as setting expiration dates or automatically rotating keys. You can develop workflows to automate these processes by using tools such as Azure PowerShell or the Azure SDKs.
- To enforce time-limited access to APIs, API publishers might be able to use policies with subscription keys, or use a mechanism that provides built-in expiration such as token-based authentication.

## Scope of subscriptions

You can associate subscriptions with various scopes: [product](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-add-products), all APIs, or an individual API.

### Subscriptions for a product

Traditionally, you associate subscriptions in API Management with a single [product](https://learn.microsoft.com/en-us/azure/api-management/api-management-terminology) scope. Developers:

- Find the list of products on the developer portal.
- Submit subscription requests for the products they want to use.
- Access the APIs in the product by using the keys in those subscriptions that are approved either automatically or by API publishers.

Currently, the developer portal only shows the product scope subscriptions under the **User Profile** section.

![Diagram showing the traditional flow for a Product scope subscription. Developers submit a subscription request for a product and receive a key to access it.](https://learn.microsoft.com/en-us/azure/api-management/media/api-management-subscriptions/product-subscription.png)

### Subscriptions for all APIs or an individual API

You can also create keys that grant access to either:

- A single API, or
- All APIs within an API Management instance.

In these cases, you don't need to create a product and add APIs to it first.

### All-access subscription

Each API Management instance comes with a built-in all-access subscription that grants access to all APIs. This service-scoped subscription makes it straightforward for service owners to test and debug APIs within the test console.

Warning

The all-access subscription enables access to every API in the API Management instance. Only authorized users should use this subscription. Never use this subscription for routine API access or embed the all-access subscription key in client apps.

If you're using an API-scoped subscription, an all-APIs subscription, or the built-in all-access subscription, policies configured at the product scope aren't applied to requests from that subscription.

### Standalone subscriptions

API Management also allows _standalone_ subscriptions, which aren't associated with a developer account. This feature is useful in scenarios such as several developers or teams sharing a subscription.

Creating a subscription without assigning an owner makes it a standalone subscription. To grant developers and the rest of your team access to the standalone subscription key, either:

- Manually share the subscription key.
- Use a custom system to make the subscription key available to your team.

You can't directly assign subscriptions in API Management to Microsoft Entra ID security groups. To provide subscription access to multiple users in a group, create a standalone subscription and distribute the subscription keys to group members, or integrate with Microsoft Entra ID for authentication and use policies to control API access based on group membership.

## Create and manage subscriptions in Azure portal

API publishers (administrators or developers with appropriate permissions) can [create subscriptions](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-create-subscriptions) directly in the Azure portal by signing in to their API Management instance. API consumers can't create subscriptions through the Azure portal; they typically request subscriptions through the developer portal or receive them from API publishers.

When you create a subscription in the portal, it's in the **Active** state, which means a subscriber can call an associated API by using a valid subscription key. You can change the state of the subscription as needed. For example, you can suspend, cancel, or delete any subscription (including the built-in all-access subscription) to prevent API access.

## Use a subscription key

Subscribers can use an API Management subscription key in two ways:

- Add the **Ocp-Apim-Subscription-Key** HTTP header to the request, passing the value of a valid subscription key.
- Include the **subscription-key** query parameter and a valid value in the URL. The query parameter is checked only if the header isn't present.

Tip

**Ocp-Apim-Subscription-Key** is the default name of the subscription key header, and **subscription-key** is the default name of the query parameter. If desired, you can modify these names in the settings for each API. For example, in the portal, update these names on the **Settings** tab of an API.

When included in a request header or query parameter, the subscription key is by default passed to the backend and might be exposed in backend monitoring logs or other systems. If this data is sensitive, you can configure a policy at the end of the `inbound` section to remove the subscription key header ( [`set-header`](https://learn.microsoft.com/en-us/azure/api-management/set-header-policy)) or query parameter ( [`set-query-parameter`](https://learn.microsoft.com/en-us/azure/api-management/set-query-parameter-policy)).

## Enable or disable subscription requirement for API or product access

By default when you create an API, a subscription key is required for API access. Similarly, when you create a product, by default a subscription key is required to access any API that you add to the product. Under certain scenarios, an API publisher might want to publish a product or a particular API to the public without the requirement of subscriptions. While a publisher could choose to enable unsecured (anonymous) access to certain APIs, configuring another mechanism to secure client access is recommended.

Caution

Be careful when configuring a product or an API that doesn't require a subscription. This configuration might be too permissive and can make an API more vulnerable to certain [API security threats](https://learn.microsoft.com/en-us/azure/api-management/mitigate-owasp-api-threats#security-misconfiguration).

Open products have the **Requires subscription** setting disabled, which means that users don't need to subscribe to them. For this reason, open products don't appear on the **Products** page of the developer portal.

You can disable the subscription requirement when you create an API or product, or later.

To disable the subscription requirement by using the portal:

- **Disable requirement for product** \- On the **Settings** page of the product, disable **Requires subscription**.
- **Disable requirement for API** \- In the **Settings** page of the API, disable **Subscription required**.

After the subscription requirement is disabled, the selected API or APIs can be accessed without a subscription key.

## How API Management handles requests with or without subscription keys

### API request with a subscription key

When API Management receives an API request from a client with a subscription key, it handles the request according to these rules:

1. It checks if the key is valid and associated with an _active subscription_, defined as:

   - A subscription scoped to the API.
   - A subscription scoped to a product assigned to the API.
   - A subscription scoped to all APIs.
   - The service-scoped subscription (built in all access subscription).

If the key is valid for an active subscription at an appropriate scope, API Management grants access. It applies policies depending on the configuration of the policy definition at that scope.

2. If the key isn't valid but a product exists that includes the API without requiring a subscription (an _open_ product), API Management ignores the key and handles the request as an API request without a subscription key (see the following section).

3. Otherwise, API Management denies access (401 Access denied error).

### API request without a subscription key

When API Management receives an API request from a client without a subscription key, it handles the request according to these rules:

1. It checks for the existence of a product that includes the API but doesn't require a subscription (an _open_ product). If the open product exists, API Management handles the request in the context of the APIs, policies, and access rules configured for the open product. An API can be associated with at most one open product.
2. If an open product including the API isn't found, API Management checks whether the API requires a subscription. If a subscription isn't required, API Management handles the request in the context of that API and operation.
3. If no configured product or API is found, then API Management denies access (401 Access denied error).

### Summary table

The following table summarizes how the gateway handles API requests with or without subscription keys in different scenarios. The table notes configurations that could potentially enable unintended, anonymous API access.

| All products assigned to API require subscription | API requires subscription | API call with subscription key | API call without subscription key | Typical scenarios |
| --- | --- | --- | --- | --- |
| ✔️ | ✔️ | Access allowed:<br>• Product-scoped key<br>• API-scoped key<br>• All APIs-scoped key<br>• Service-scoped key<br>Access denied:<br>• Other key not scoped to applicable product or API | Access denied | Protected API access using product-scoped or API-scoped subscription |
| ✔️ | ❌ | Access allowed:<br>• Product-scoped key<br>• API-scoped key<br>• All APIs-scoped key<br>• Service-scoped key<br>• Other key not scoped to applicable product or API | Access allowed (API context) | • Protected API access with product-scoped subscription<br>• Anonymous access to API. If anonymous access isn’t intended, configure API-level policies to enforce authentication and authorization. |
| ❌1 | ✔️ | Access allowed:<br>• Product-scoped key<br>• API-scoped key<br>• All APIs-scoped key<br>• Service-scoped key<br>Access denied:<br>• Other key not scoped to applicable product or API | Access allowed (open product context) | • Protected API access with API-scoped subscription<br>• Anonymous access to API. If anonymous access isn’t intended, configure with product policies to enforce authentication and authorization |
| ❌1 | ❌ | Access allowed:<br>• Product-scoped key<br>• API-scoped key<br>• All APIs-scoped key<br>• Service-scoped key<br>• Other key not scoped to applicable product or API | Access allowed (open product context) | Anonymous access to API. If anonymous access isn’t intended, configure with product policies to enforce authentication and authorization |

1 An open product exists that's associated with the API.

### Considerations

- API access in a product context is the same, whether the product is published or not. Unpublishing the product hides it from the developer portal, but it doesn't invalidate new or existing subscription keys.
- If an API doesn't require subscription authentication, any API request that includes a subscription key is treated the same as a request without a subscription key. The subscription key is ignored.
- API access "context" means the policies and access controls that are applied at a particular scope (for example, API or product).

## Related content

Get more information on API Management:

- Learn how API Management [policies](https://learn.microsoft.com/en-us/azure/api-management/set-edit-policies#configure-policies-at-different-scopes) get applied at different scopes.
- Learn other [concepts](https://learn.microsoft.com/en-us/azure/api-management/api-management-terminology) in API Management.
- Follow our [tutorials](https://learn.microsoft.com/en-us/azure/api-management/import-and-publish) to learn more about API Management.
- Check our [FAQ page](https://learn.microsoft.com/en-us/azure/api-management/api-management-faq) for common questions.

* * *
