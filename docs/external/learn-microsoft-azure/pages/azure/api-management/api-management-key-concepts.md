# What is Azure API Management?

**APPLIES TO: All API Management tiers**

This article provides an overview of common scenarios and key components of Azure API Management. Azure API Management is a hybrid, multicloud management platform for APIs across all environments. As a platform-as-a-service, API Management supports the complete API lifecycle.

Tip

If you're already familiar with API Management and ready to start, see these resources:

- [Features and service tiers](https://learn.microsoft.com/en-us/azure/api-management/api-management-features)
- [Create an API Management instance](https://learn.microsoft.com/en-us/azure/api-management/get-started-create-service-instance)
- [Import and publish an API](https://learn.microsoft.com/en-us/azure/api-management/import-and-publish)
- [API Management policies](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-policies)

## Scenarios

APIs enable digital experiences, simplify application integration, underpin new digital products, and make data and services reusable and universally accessible. ​With the proliferation and increasing dependency on APIs, organizations need to manage them as first-class assets throughout their lifecycle.​

![Diagram showing role of APIs in connected experiences.](https://learn.microsoft.com/en-us/azure/api-management/media/api-management-key-concepts/apis-connected-experiences.png)

Azure API Management helps organizations meet these challenges:

- Provide a comprehensive API platform for different stakeholders and teams to produce and manage APIs
- Abstract backend architecture diversity and complexity from API consumers
- Securely expose services hosted on and outside of Azure as APIs
- Protect, accelerate, and observe APIs
- Enable API discovery and consumption by internal and external users

Common scenarios include:

- **Unlocking legacy assets** \- APIs are used to abstract and modernize legacy backends and make them accessible from new cloud services and modern applications. APIs allow innovation without the risk, cost, and delays of migration.
- **API-centric app integration** \- APIs are easily consumable, standards-based, and self-describing mechanisms for exposing and accessing data, applications, and processes. They simplify and reduce the cost of app integration.
- **Multi-channel user experiences** \- APIs are frequently used to enable user experiences such as web, mobile, wearable, or Internet of Things applications. Reuse APIs to accelerate development and ROI.
- **B2B integration** \- APIs exposed to partners and customers lower the barrier to integrate business processes and exchange data between business entities. APIs eliminate the overhead inherent in point-to-point integration. Especially with self-service discovery and onboarding enabled, APIs are the primary tools for scaling B2B integration.

Tip

Visit [aka.ms/apimlove](https://aka.ms/apimlove) for a library of useful resources, including videos, blogs, and customer stories about using Azure API Management.

## API Management components

Azure API Management is made up of an API _gateway_, a _management plane_, and a _developer portal_, with features designed for different audiences in the API ecosystem. These components are Azure-hosted and fully managed by default. API Management is available in various [tiers](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts#api-management-tiers) differing in capacity and features.

![Diagram showing key components of Azure API Management.](https://learn.microsoft.com/en-us/azure/api-management/media/api-management-key-concepts/api-management-components.png)

## API gateway

All requests from client applications first reach the API gateway (also called _data plane_ or _runtime_), which then forwards them to respective backend services. The API gateway acts as a facade to the backend services, allowing API providers to abstract API implementations and evolve backend architecture without impacting API consumers. The gateway enables consistent configuration of routing, security, throttling, caching, and observability.

Specifically, the gateway:

- Acts as a facade to backend services by accepting API calls and routing them to appropriate backends
- Verifies [API keys](https://learn.microsoft.com/en-us/azure/api-management/api-management-subscriptions) and other credentials such as [JWTs and certificates](https://learn.microsoft.com/en-us/azure/api-management/api-management-access-restriction-policies) presented with requests
- Enforces [usage quotas and rate limits](https://learn.microsoft.com/en-us/azure/api-management/api-management-access-restriction-policies)
- Optionally transforms requests and responses as specified in [policy statements](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-policies)
- If configured, [caches responses](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-cache) to improve response latency and minimize the load on backend services
- Emits logs, metrics, and traces for [monitoring, reporting, and troubleshooting](https://learn.microsoft.com/en-us/azure/api-management/observability)

### Self-hosted gateway

With the [self-hosted gateway](https://learn.microsoft.com/en-us/azure/api-management/self-hosted-gateway-overview), an API provider can deploy the API gateway to the same environments where they host their APIs, to optimize API traffic and ensure compliance with local regulations and guidelines. The self-hosted gateway enables organizations with hybrid IT infrastructure to manage APIs hosted on-premises and across clouds from a single API Management service in Azure.

The self-hosted gateway is packaged as a Linux-based Docker container and is commonly deployed to Kubernetes, including to Azure Kubernetes Service and [Azure Arc-enabled Kubernetes](https://learn.microsoft.com/en-us/azure/api-management/how-to-deploy-self-hosted-gateway-azure-arc).

More information:

- [API gateway in Azure API Management](https://learn.microsoft.com/en-us/azure/api-management/api-management-gateways-overview)

## Management plane

API providers interact with the service through the management plane (also called _control plane_), which provides full access to the API Management service capabilities.

Customers interact with the management plane through Azure tools that include the Azure portal, Azure PowerShell, Azure CLI, a [Visual Studio Code extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-apimanagement&ssr=false#overview), and a REST API. Or they can interact through client SDKs in several popular programming languages.

Use the management plane to:

- Provision and configure API Management service settings.
- Define or import API schemas from a wide range of sources. Including, OpenAPI, WSDL, OData definitions, Azure compute services, WebSocket, GraphQL, and gRPC backends.
- Package APIs into products.
- Set up [policies](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts#policies) like quotas or transformations on the APIs.
- Get insights from analytics.
- Manage users such as app developers.

## Developer portal

The open-source [developer portal](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts#developer-portal) is an automatically generated, fully customizable website with the documentation of your APIs.

![Screenshot of API Management developer portal - administrator mode.](https://learn.microsoft.com/en-us/azure/api-management/media/api-management-key-concepts/cover.png)

API providers can customize the look and feel of the developer portal by adding custom content, customizing styles, and adding their branding. Extend the developer portal further by [self-hosting](https://learn.microsoft.com/en-us/azure/api-management/developer-portal-self-host).

API consumers such as app developers access the open-source developer portal to discover the APIs, onboard to use them, and learn how to consume them in applications. (APIs can also be exported to the [Power Platform](https://learn.microsoft.com/en-us/azure/api-management/export-api-power-platform) for discovery and use by citizen developers.)

When they use the developer portal, API consumers can:

- Read API documentation
- Call an API via the interactive console
- Create an account and subscribe to get API keys
- Access analytics on their own usage
- Download API definitions
- Manage API keys

## Federated API management with workspaces

For organizations that want to empower decentralized teams to develop and manage their own APIs with the advantages of centralized API governance and discovery, API Management offers first-class support for a federated API management model with _workspaces_.

In API Management, workspaces bring a new level of autonomy to an organization's API teams, enabling them to create, manage, and publish APIs faster, more reliably, securely, and productively within an API Management service. By providing isolated administrative access and API runtime, workspaces empower API teams while allowing the API platform team to retain oversight. This includes central monitoring, enforcement of API policies and compliance, and publishing APIs for discovery through a unified developer portal.

**More information**:

- [Workspaces in API Management](https://learn.microsoft.com/en-us/azure/api-management/workspaces-overview)

## API Management tiers

API Management is offered in various pricing tiers to meet the needs of different customers. Each tier offers a distinct combination of features, performance, capacity limits, scalability, SLA, and pricing for different scenarios. The tiers are grouped as follows:

- **Classic** \- The original API Management offering, including the Developer, Basic, Standard, and Premium tiers. The Premium tier is designed for enterprises that require access to private backends, enhanced security features, multi-region deployments, availability zones, and high scalability. The Developer tier is an economical option for nonproduction use, while the Basic, Standard, and Premium tiers are production-ready tiers.
- **V2** \- A new set of tiers that offer fast provisioning and scaling, including Basic v2 for development and testing, and Standard v2 and Premium v2 for production workloads. Standard v2 and Premium v2 support virtual network integration for simplified connection to network-isolated backends. Premium v2 also supports virtual network injection for full isolation of network traffic to and from the gateway.
- **Consumption** \- A serverless gateway for managing APIs that scales based on demand and bills per execution. This tier is designed for applications with serverless compute, microservices-based architectures, and variable traffic patterns.

**More information**:

- [Feature-based comparison of the Azure API Management tiers](https://learn.microsoft.com/en-us/azure/api-management/api-management-features)
- [V2 service tiers](https://learn.microsoft.com/en-us/azure/api-management/v2-service-tiers-overview)
- [Understanding API Management limits](https://learn.microsoft.com/en-us/azure/api-management/service-limits)
- [API Management pricing](https://azure.microsoft.com/pricing/details/api-management/)

## Integration with Microsoft services

API Management integrates with many complementary Microsoft and Azure services to create enterprise solutions, including:

- **[Azure API Center](https://learn.microsoft.com/en-us/azure/api-center/overview)** to build a complete inventory of APIs​ in the organization - regardless of their type, lifecycle stage, or deployment location​ - for API discovery, reuse, and governance
- **[Azure Copilot](https://learn.microsoft.com/en-us/azure/copilot/overview)** to help author API Management policies or explain already configured policies​
- **[Microsoft Foundry](https://learn.microsoft.com/en-us/azure/api-management/azure-ai-foundry-api)** to govern AI model endpoints deployed in Microsoft Foundry as APIs.
- **[Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)** for secure safekeeping and management of [client certificates](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-mutual-certificates) and [secrets​](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-properties)
- **[Azure Monitor](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-use-azure-monitor)** for logging, reporting, and alerting on management operations, systems events, and API requests​
- **[Application Insights](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-app-insights)** for live metrics, end-to-end tracing, and troubleshooting
- **[Virtual networks](https://learn.microsoft.com/en-us/azure/api-management/virtual-network-concepts)**, **[private endpoints](https://learn.microsoft.com/en-us/azure/api-management/private-endpoint)**, **[Application Gateway](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-integrate-internal-vnet-appgateway)**, and **[Azure Front Door](https://learn.microsoft.com/en-us/azure/api-management/front-door-api-management)** for network-level protection​
- **[Microsoft Defender for APIs](https://learn.microsoft.com/en-us/azure/api-management/protect-with-defender-for-apis)** and **[Azure DDoS Protection](https://learn.microsoft.com/en-us/azure/api-management/protect-with-ddos-protection)** for runtime protection against malicious attacks​
- **Microsoft Entra ID** for [developer authentication](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-aad) and [request authorization](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-protect-backend-with-aad) ​
- **[Event Hubs](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-log-event-hubs)** for streaming events​
- **[Azure Redis](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-cache-external)** for caching responses​ with Azure Cache for Redis or Azure Managed Redis​
- Several Azure compute offerings commonly used to build and host APIs on Azure, including **[Functions](https://learn.microsoft.com/en-us/azure/api-management/import-function-app-as-api)**, **[Logic Apps](https://learn.microsoft.com/en-us/azure/api-management/import-logic-app-as-api)**, **[Web Apps](https://learn.microsoft.com/en-us/azure/api-management/import-app-service-as-api)**, **[Service Fabric](https://learn.microsoft.com/en-us/azure/api-management/how-to-configure-service-fabric-backend)**, and others.​
- Azure database offerings, including [Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/api-management/cosmosdb-data-source-policy), enabling direct CRUD (Create, Read, Update, Delete) operations without requiring intermediate compute resources.

**More information**:

- [Basic enterprise integration](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/enterprise-integration/basic-enterprise-integration?toc=%2Fazure%2Fapi-management%2Ftoc.json&bc=/azure/api-management/breadcrumb/toc.json)
- [Landing zone accelerator](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/scenarios/app-platform/api-management/landing-zone-accelerator?toc=%2Fazure%2Fapi-management%2Ftoc.json&bc=/azure/api-management/breadcrumb/toc.json)
- [AI gateway capabilities in API Management](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities)
- [Synchronize APIs to API Center from API Management](https://learn.microsoft.com/en-us/azure/api-center/synchronize-api-management-apis?toc=/azure/api-management/toc.json&bc=/azure/api-management/breadcrumb/toc.json)

## Key concepts

### APIs

APIs are the foundation of an API Management service instance. Each API represents a set of _operations_ available to app developers. Each API contains a reference to the backend service that implements the API, and its operations map to backend operations.

Operations in API Management are highly configurable. You have control over URL mapping, query and path parameters, request and response content, and operation response caching.

**More information**:

- [Import and publish your first API](https://learn.microsoft.com/en-us/azure/api-management/import-and-publish)
- [Mock API responses](https://learn.microsoft.com/en-us/azure/api-management/mock-api-responses)

### Products

Products are how APIs are surfaced to API consumers such as app developers. Products in API Management have one or more APIs and can be _open_ or _protected_. Protected products require a subscription key, while open products can be consumed freely.

When a product is ready for use by consumers, it can be published. Once published, it can be viewed or subscribed to by users through the developer portal. Subscription approval is configured at the product level and can either require an administrator's approval or be automatic.

**More information**:

- [Create and publish a product](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-add-products)
- [Subscriptions in API Management](https://learn.microsoft.com/en-us/azure/api-management/api-management-subscriptions)

### Users and groups

Users (API consumers) can be created or invited to join by service administrators, or they can sign up from the [developer portal](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts#developer-portal). Each user is a member of one or more groups, and can subscribe to the products that grant visibility to those groups.

API Management has the following built-in groups:

- **Developers** \- Authenticated developer portal users that build applications using your APIs. Developers are granted access to the developer portal and build applications that call the operations of an API.

- **Guests** \- Unauthenticated developer portal users, such as prospective customers visiting the developer portal. They can be granted certain read-only access, such as the ability to view APIs but not call them.

API Management service owners can also create custom groups or use external groups in an [associated Microsoft Entra tenant](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-aad) to give users visibility and access to API products. For example, create a custom group for developers in a partner organization to access a specific subset of APIs in a product. A user can belong to more than one group.

**More information**:

- [How to create and use groups](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-create-groups)
- [How to manage user accounts](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-create-or-invite-developers)

### Workspaces

Workspaces support a federated API management model by allowing decentralized API development teams to manage and productize their own APIs, while a central API platform team maintains the API Management infrastructure. Each workspace contains APIs, products, subscriptions, and related entities that are accessible only to the workspace collaborators. Access is controlled through Azure role-based access control (RBAC). Each workspace is associated with one or more workspace gateways that route API traffic to its backend services.

**More information**:

- [Workspaces in API Management](https://learn.microsoft.com/en-us/azure/api-management/workspaces-overview)

### Policies

With [policies](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-policies), an API provider can change the behavior of an API through configuration. Policies are a collection of statements that are executed sequentially on the request or response of an API. Popular statements include format conversion from XML to JSON and call-rate limiting to restrict the number of incoming calls from a developer. For a complete list, see [API Management policies](https://learn.microsoft.com/en-us/azure/api-management/api-management-policies).

Policy expressions can be used as attribute values or text values in many of the API Management policies. Some policies such as the [Control flow](https://learn.microsoft.com/en-us/azure/api-management/choose-policy) and [Set variable](https://learn.microsoft.com/en-us/azure/api-management/set-variable-policy) policies are based on policy expressions.

Policies can be applied at different scopes, depending on your needs: global (all APIs), a workspace, a product, a specific API, or an API operation.

**More information**:

- [Transform and protect your API](https://learn.microsoft.com/en-us/azure/api-management/transform-api).
- [Policy expressions](https://learn.microsoft.com/en-us/azure/api-management/api-management-policy-expressions)

## Next steps

Complete the following quickstart and start using Azure API Management:

[Create an Azure API Management instance by using the Azure portal](https://learn.microsoft.com/en-us/azure/api-management/get-started-create-service-instance)

* * *
