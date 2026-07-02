# List applications

Namespace: microsoft.graph

Get the list of [applications](https://learn.microsoft.com/en-us/graph/api/resources/application?view=graph-rest-1.0) in this organization. This API also returns [agentIdentityBlueprint](https://learn.microsoft.com/en-us/graph/api/resources/agentidentityblueprint?view=graph-rest-1.0) objects, which are identified by the **@odata.type** property of `#microsoft.graph.agentIdentityBlueprint`.

When calling this API using tokens issued for a personal Microsoft account, it will return the apps owned by the personal Microsoft account. The notion of organizations doesn't exist for personal Microsoft accounts. To list applications owned by a specific personal Microsoft account, this API requires the _User.Read_ permission in addition to _Application.Read.All_ or _Application.ReadWrite.All_.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | Application.Read.All | Application.ReadWrite.All, Directory.ReadWrite.All, Directory.Read.All |
| Delegated (personal Microsoft account) | Application.Read.All and User.Read | Application.ReadWrite.All and User.Read |
| Application | Application.Read.All | Application.ReadWrite.OwnedBy, Application.ReadWrite.All, Directory.Read.All |

Important

For delegated access using work or school accounts where the signed-in user is acting on another user, they must be assigned a supported [Microsoft Entra role](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference?toc=%2Fgraph%2Ftoc.json) or a custom role that grants the permissions required for this operation. This operation supports the following built-in roles, which provide only the least privilege necessary:

- A non-admin member or guest user with default user permissions
- Application Developer - read properties of application they own
- Directory Readers - read standard properties
- Global Secure Access Administrator - read standard properties
- Global Reader
- Directory Writers
- Hybrid Identity Administrator
- Security Administrator
- Cloud Application Administrator
- Application Administrator

## HTTP request

HTTP

Copy

```http
GET /applications
```

## Optional query parameters

This method supports the `$count`, `$expand`, `$filter`, `$orderby`, `$search`, `$select`, and `$top` [OData query parameters](https://learn.microsoft.com/en-us/graph/query-parameters) to help customize the response. Some relationships also support `$filter`. The default and maximum page sizes are 100 and 999 application objects respectively. Some queries are supported only when you use the **ConsistencyLevel** header set to `eventual` and `$count`. For more information, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries).

By default, this API doesn't return the value of the **key** in the **keyCredentials** property when listing all applications. To retrieve the public key info in **key**, the **keyCredentials** property must be specified in a `$select` query. For example, `$select=id,appId,keyCredentials`.

The use of `$select` to get **keyCredentials** for applications has a throttling limit of 150 requests per minute for every tenant.

The **managerApplications** property is not returned by default. To retrieve it, use `$select=managerApplications` or include it in a `$select` query with other properties. For example, `$select=id,appId,managerApplications`.

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| ConsistencyLevel | eventual. This header and `$count` are required when using `$search`, or in specific usage of `$filter`. For more information about the use of **ConsistencyLevel** and `$count`, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries). |

## Request body

Don't supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a collection of [application](https://learn.microsoft.com/en-us/graph/api/resources/application?view=graph-rest-1.0) and [agentIdentityBlueprint](https://learn.microsoft.com/en-us/graph/api/resources/agentidentityblueprint?view=graph-rest-1.0) objects in the response body.

## Examples

### Example 1: Get the list of applications

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applications
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Applications.GetAsync();
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
applications, err := graphClient.Applications().Get(context.Background(), nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ApplicationCollectionResponse result = graphClient.applications().get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let applications = await client.api('/applications')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$result = $graphServiceClient->applications()->get()->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplication
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

result = await graph_client.applications.get()
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#applications",
  "value": [\
    {\
      "appId": "00000000-0000-0000-0000-000000000000",\
      "identifierUris": [ "http://contoso/" ],\
      "displayName": "My app",\
      "publisherDomain": "contoso.com",\
      "signInAudience": "AzureADMyOrg"\
    }\
  ]
}
```

### Example 2: Get only a count of applications

#### Request

The following example shows a request. This request requires the **ConsistencyLevel** header set to `eventual` because `$count` is in the request. For more information about the use of **ConsistencyLevel** and `$count`, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries).

> **Note:** The `$count` and `$search` query parameters are currently not available in Azure AD B2C tenants.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applications/$count
ConsistencyLevel: eventual
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.Applications.Count.GetAsync((requestConfiguration) =>
{
	requestConfiguration.Headers.Add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  abstractions "github.com/microsoft/kiota-abstractions-go"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplications "github.com/microsoftgraph/msgraph-sdk-go/applications"
	  //other-imports
)

headers := abstractions.NewRequestHeaders()
headers.Add("ConsistencyLevel", "eventual")

configuration := &graphapplications.Applications$countRequestBuilderGetRequestConfiguration{
	Headers: headers,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
graphClient.Applications().Count().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

graphClient.applications().count().get(requestConfiguration -> {
	requestConfiguration.headers.add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let int32 = await client.api('/applications/$count')
	.header('ConsistencyLevel','eventual')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Applications\Count\CountRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new CountRequestBuilderGetRequestConfiguration();
$headers = [\
		'ConsistencyLevel' => 'eventual',\
	];
$requestConfiguration->headers = $headers;

$graphServiceClient->applications()->count()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplicationCount -ConsistencyLevel eventual
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.applications.count.count_request_builder import CountRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

request_configuration = RequestConfiguration()
request_configuration.headers.add("ConsistencyLevel", "eventual")

await graph_client.applications.count.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: text/plain

893
```

### Example 3: Use $filter and $top to get one application with a display name that starts with 'a' including a count of returned objects

#### Request

The following example shows a request. This request requires the **ConsistencyLevel** header set to `eventual` and the `$count=true` query string because the request has both the `$orderby` and `$filter` query parameters. For more information about the use of **ConsistencyLevel** and `$count`, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries).

> **Note:** The `$count` and `$search` query parameters are currently not available in Azure AD B2C tenants.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_3_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applications?$filter=startswith(displayName, 'a')&$count=true&$top=1&$orderby=displayName
ConsistencyLevel: eventual
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Applications.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "startswith(displayName, 'a')";
	requestConfiguration.QueryParameters.Count = true;
	requestConfiguration.QueryParameters.Top = 1;
	requestConfiguration.QueryParameters.Orderby = new string []{ "displayName" };
	requestConfiguration.Headers.Add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  abstractions "github.com/microsoft/kiota-abstractions-go"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplications "github.com/microsoftgraph/msgraph-sdk-go/applications"
	  //other-imports
)

headers := abstractions.NewRequestHeaders()
headers.Add("ConsistencyLevel", "eventual")

requestFilter := "startswith(displayName, 'a')"
requestCount := true
requestTop := int32(1)

requestParameters := &graphapplications.ApplicationsRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
	Count: &requestCount,
	Top: &requestTop,
	Orderby: [] string {"displayName"},
}
configuration := &graphapplications.ApplicationsRequestBuilderGetRequestConfiguration{
	Headers: headers,
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
applications, err := graphClient.Applications().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ApplicationCollectionResponse result = graphClient.applications().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "startswith(displayName, 'a')";
	requestConfiguration.queryParameters.count = true;
	requestConfiguration.queryParameters.top = 1;
	requestConfiguration.queryParameters.orderby = new String []{"displayName"};
	requestConfiguration.headers.add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let applications = await client.api('/applications')
	.header('ConsistencyLevel','eventual')
	.filter('startswith(displayName, \'a\')')
	.orderby('displayName')
	.top(1)
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Applications\ApplicationsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ApplicationsRequestBuilderGetRequestConfiguration();
$headers = [\
		'ConsistencyLevel' => 'eventual',\
	];
$requestConfiguration->headers = $headers;

$queryParameters = ApplicationsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "startswith(displayName, 'a')";
$queryParameters->count = true;
$queryParameters->top = 1;
$queryParameters->orderby = ["displayName"];
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->applications()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplication -Filter "startswith(displayName, 'a')" -CountVariable CountVar -Top 1 -Sort "displayName"  -ConsistencyLevel eventual
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.applications.applications_request_builder import ApplicationsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ApplicationsRequestBuilder.ApplicationsRequestBuilderGetQueryParameters(
		filter = "startswith(displayName, 'a')",
		count = True,
		top = 1,
		orderby = ["displayName"],
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)
request_configuration.headers.add("ConsistencyLevel", "eventual")

result = await graph_client.applications.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context":"https://graph.microsoft.com/v1.0/$metadata#applications",
  "@odata.count":1,
  "value":[\
    {\
      "appId": "00000000-0000-0000-0000-000000000000",\
      "identifierUris": [ "http://contoso/" ],\
      "displayName":"a",\
      "publisherDomain": "contoso.com",\
      "signInAudience": "AzureADMyOrg"\
    }\
  ]
}
```

### Example 4: Use $search to get applications with display names that contain the letters 'Web' including a count of returned objects

#### Request

The following example shows a request. This request requires the **ConsistencyLevel** header set to `eventual` because `$search` and the `$count=true` query string is in the request. For more information about the use of **ConsistencyLevel** and `$count`, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries).

> **Note:** The `$count` and `$search` query parameters are currently not available in Azure AD B2C tenants.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_4_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applications?$search="displayName:Web"&$count=true&$select=appId,identifierUris,displayName,publisherDomain,signInAudience
ConsistencyLevel: eventual
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Applications.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Search = "\"displayName:Web\"";
	requestConfiguration.QueryParameters.Count = true;
	requestConfiguration.QueryParameters.Select = new string []{ "appId","identifierUris","displayName","publisherDomain","signInAudience" };
	requestConfiguration.Headers.Add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  abstractions "github.com/microsoft/kiota-abstractions-go"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplications "github.com/microsoftgraph/msgraph-sdk-go/applications"
	  //other-imports
)

headers := abstractions.NewRequestHeaders()
headers.Add("ConsistencyLevel", "eventual")

requestSearch := "\"displayName:Web\""
requestCount := true

requestParameters := &graphapplications.ApplicationsRequestBuilderGetQueryParameters{
	Search: &requestSearch,
	Count: &requestCount,
	Select: [] string {"appId","identifierUris","displayName","publisherDomain","signInAudience"},
}
configuration := &graphapplications.ApplicationsRequestBuilderGetRequestConfiguration{
	Headers: headers,
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
applications, err := graphClient.Applications().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ApplicationCollectionResponse result = graphClient.applications().get(requestConfiguration -> {
	requestConfiguration.queryParameters.search = "\"displayName:Web\"";
	requestConfiguration.queryParameters.count = true;
	requestConfiguration.queryParameters.select = new String []{"appId", "identifierUris", "displayName", "publisherDomain", "signInAudience"};
	requestConfiguration.headers.add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let applications = await client.api('/applications')
	.header('ConsistencyLevel','eventual')
	.search('displayName:Web')
	.select('appId,identifierUris,displayName,publisherDomain,signInAudience')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Applications\ApplicationsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ApplicationsRequestBuilderGetRequestConfiguration();
$headers = [\
		'ConsistencyLevel' => 'eventual',\
	];
$requestConfiguration->headers = $headers;

$queryParameters = ApplicationsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->search = "\"displayName:Web\"";
$queryParameters->count = true;
$queryParameters->select = ["appId","identifierUris","displayName","publisherDomain","signInAudience"];
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->applications()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplication -Search '"displayName:Web"' -CountVariable CountVar -Property "appId,identifierUris,displayName,publisherDomain,signInAudience"  -ConsistencyLevel eventual
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.applications.applications_request_builder import ApplicationsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ApplicationsRequestBuilder.ApplicationsRequestBuilderGetQueryParameters(
		search = "\"displayName:Web\"",
		count = True,
		select = ["appId","identifierUris","displayName","publisherDomain","signInAudience"],
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)
request_configuration.headers.add("ConsistencyLevel", "eventual")

result = await graph_client.applications.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
  "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#applications(appId,identifierUris,displayName,publisherDomain,signInAudience)",
  "@odata.count":1396,
  "value":[\
    {\
      "appId": "00000000-0000-0000-0000-000000000000",\
      "identifierUris": [ "http://contoso/" ],\
      "displayName":"'DotNetWeb-App' ",\
      "publisherDomain": "contoso.com",\
      "signInAudience": "AzureADMyOrg"\
    }\
  ]
}
```

### Example 5: Get applications with less than two owners

#### Request

The following example shows a request. This request requires the **ConsistencyLevel** header set to `eventual` because `$count` is in the request. For more information about the use of **ConsistencyLevel** and `$count`, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries).

> **Note:** The `$count` and `$search` query parameters are currently not available in Azure AD B2C tenants.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_5_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applications?$filter=owners/$count eq 0 or owners/$count eq 1&$count=true&$select=id,displayName
ConsistencyLevel: eventual
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Applications.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "owners/$count eq 0 or owners/$count eq 1";
	requestConfiguration.QueryParameters.Count = true;
	requestConfiguration.QueryParameters.Select = new string []{ "id","displayName" };
	requestConfiguration.Headers.Add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  abstractions "github.com/microsoft/kiota-abstractions-go"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplications "github.com/microsoftgraph/msgraph-sdk-go/applications"
	  //other-imports
)

headers := abstractions.NewRequestHeaders()
headers.Add("ConsistencyLevel", "eventual")

requestFilter := "owners/$count eq 0 or owners/$count eq 1"
requestCount := true

requestParameters := &graphapplications.ApplicationsRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
	Count: &requestCount,
	Select: [] string {"id","displayName"},
}
configuration := &graphapplications.ApplicationsRequestBuilderGetRequestConfiguration{
	Headers: headers,
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
applications, err := graphClient.Applications().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ApplicationCollectionResponse result = graphClient.applications().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "owners/$count eq 0 or owners/$count eq 1";
	requestConfiguration.queryParameters.count = true;
	requestConfiguration.queryParameters.select = new String []{"id", "displayName"};
	requestConfiguration.headers.add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let applications = await client.api('/applications')
	.header('ConsistencyLevel','eventual')
	.filter('owners/$count eq 0 or owners/$count eq 1')
	.select('id,displayName')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Applications\ApplicationsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ApplicationsRequestBuilderGetRequestConfiguration();
$headers = [\
		'ConsistencyLevel' => 'eventual',\
	];
$requestConfiguration->headers = $headers;

$queryParameters = ApplicationsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "owners/\$count eq 0 or owners/\$count eq 1";
$queryParameters->count = true;
$queryParameters->select = ["id","displayName"];
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->applications()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplication -Filter "owners/`$count eq 0 or owners/`$count eq 1" -CountVariable CountVar -Property "id,displayName"  -ConsistencyLevel eventual
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.applications.applications_request_builder import ApplicationsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ApplicationsRequestBuilder.ApplicationsRequestBuilderGetQueryParameters(
		filter = "owners/$count eq 0 or owners/$count eq 1",
		count = True,
		select = ["id","displayName"],
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)
request_configuration.headers.add("ConsistencyLevel", "eventual")

result = await graph_client.applications.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#applications(id,displayName)",
    "@odata.count": 3,
    "value": [\
        {\
            "id": "89e9e6c6-a7de-4ac0-8eed-12bd867d8f27",\
            "displayName": "Box"\
        },\
        {\
            "id": "c6cb7240-c684-4e24-93f5-eb29d0d9f43b",\
            "displayName": "LinkedIn"\
        },\
        {\
            "id": "d7151835-284e-4416-adc6-96fef8a77690",\
            "displayName": "BrowserStack"\
        }\
    ]
}
```

### Example 6: Get the applications with identifierUris using the API scheme

#### Request

The following example shows a request. This request requires the **ConsistencyLevel** header set to `eventual` because `$count` is in the request. For more information about the use of **ConsistencyLevel** and `$count`, see [Advanced query capabilities on directory objects](https://learn.microsoft.com/en-us/graph/aad-advanced-queries).

- [HTTP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/application-list?view=graph-rest-1.0&tabs=http#tabpanel_6_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applications?$filter=identifierUris/any(x:startswith(x,'api://'))&$count=true
ConsistencyLevel: eventual
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Applications.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "identifierUris/any(x:startswith(x,'api://'))";
	requestConfiguration.QueryParameters.Count = true;
	requestConfiguration.Headers.Add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  abstractions "github.com/microsoft/kiota-abstractions-go"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplications "github.com/microsoftgraph/msgraph-sdk-go/applications"
	  //other-imports
)

headers := abstractions.NewRequestHeaders()
headers.Add("ConsistencyLevel", "eventual")

requestFilter := "identifierUris/any(x:startswith(x,'api://'))"
requestCount := true

requestParameters := &graphapplications.ApplicationsRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
	Count: &requestCount,
}
configuration := &graphapplications.ApplicationsRequestBuilderGetRequestConfiguration{
	Headers: headers,
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
applications, err := graphClient.Applications().Get(context.Background(), configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ApplicationCollectionResponse result = graphClient.applications().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "identifierUris/any(x:startswith(x,'api://'))";
	requestConfiguration.queryParameters.count = true;
	requestConfiguration.headers.add("ConsistencyLevel", "eventual");
});
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let applications = await client.api('/applications')
	.header('ConsistencyLevel','eventual')
	.filter('identifierUris/any(x:startswith(x,\'api://\'))')
	.get();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Applications\ApplicationsRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ApplicationsRequestBuilderGetRequestConfiguration();
$headers = [\
		'ConsistencyLevel' => 'eventual',\
	];
$requestConfiguration->headers = $headers;

$queryParameters = ApplicationsRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "identifierUris/any(x:startswith(x,'api://'))";
$queryParameters->count = true;
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->applications()->get($requestConfiguration)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplication -Filter "identifierUris/any(x:startswith(x,'api://'))" -CountVariable CountVar  -ConsistencyLevel eventual
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.applications.applications_request_builder import ApplicationsRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ApplicationsRequestBuilder.ApplicationsRequestBuilderGetQueryParameters(
		filter = "identifierUris/any(x:startswith(x,'api://'))",
		count = True,
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)
request_configuration.headers.add("ConsistencyLevel", "eventual")

result = await graph_client.applications.get(request_configuration = request_configuration)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#applications",
    "@odata.count": 15067,
    "@odata.nextLink": "https://graph.microsoft.com/v1.0/applications?$filter=identifierUris%2fany(x%3astartswith(x%2c%27api%3a%2f%2f%27))&$count=true&$skiptoken=m~AQAoOzAxOTk3MTE1OTYyMDQ4MGE4YzE0ZjlkNWM0Y2ViMjE5OzswOzA7Ow",
    "@microsoft.graph.tips": "Use $select to choose only the properties your app needs, as this can lead to performance improvements. For example: GET applications?$select=addIns,api",
    "value": [\
        {\
            "id": "000101ef-c7d0-47a0-83bd-d234347da0f3",\
            "identifierUris": [\
                "api://000101ef-c7d0-47a0-83bd-d234347da0f3"\
            ]\
        }\
    ]
}
```

* * *
