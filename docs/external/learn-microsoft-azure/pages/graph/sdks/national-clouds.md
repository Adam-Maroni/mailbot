# Access national cloud deployments with the Microsoft Graph SDKs

By default, the Microsoft Graph SDKs are configured to access data in the Microsoft Graph global service, using the `https://graph.microsoft.com` root URL to access the Microsoft Graph REST API. Developers can override this configuration to connect to [Microsoft Graph national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

## Prerequisites

You will need the following information to configure a Microsoft Graph SDK to connect to a national cloud deployment.

- Application registration details, such as client ID, tenant ID, and client secret or certificate. The application registration MUST be created in the Microsoft Entra admin center that corresponds to the national cloud deployment. See [App registration and token service root endpoints](https://learn.microsoft.com/en-us/graph/deployments#app-registration-and-token-service-root-endpoints) for details.
- The token endpoint for the national cloud deployment.
- The Microsoft Graph service root endpoint for the national cloud deployment. See [Microsoft Graph and Graph Explorer service root endpoints](https://learn.microsoft.com/en-us/graph/deployments#microsoft-graph-and-graph-explorer-service-root-endpoints) for a list of endpoints.

## Configure the SDK

In order to connect to a national cloud deployment, you must configure your [authentication provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) to connect to the correct token service endpoint. Then you must configure the SDK client to connect to the correct Microsoft Graph service root endpoint.

### Permission scopes

Any permission scope value (including the `.default` scope) that contains the Microsoft Graph domain MUST use the domain of the Microsoft Graph service root endpoint for the national cloud deployment. The shortened permission scope names, such as `User.Read` or `Mail.Send`, are also valid.

- For [incremental or dynamic consent](https://learn.microsoft.com/en-us/azure/active-directory/develop/consent-types-developer#incremental-and-dynamic-user-consent), `User.Read` and `https://graph.microsoft.us/User.Read` are equivalent for the US Government L4 national cloud.
- For [statically defined permissions](https://learn.microsoft.com/en-us/azure/active-directory/develop/consent-types-developer#request-the-permissions-in-the-app-registration-portal), or if you are using [client credentials flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow) for app-only permissions, `https://graph.microsoft.us/.default` is the correct `.default` scope value.

## Examples

The following example configures an [Interactive authentication provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers#interactive-provider) with the Microsoft Graph SDK to connect to the Microsoft Graph for US Government L4 national cloud.

- [C#](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_PHP)
- [PowerShell](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/national-clouds?tabs=csharp#tabpanel_1_typescript)

C#

Copy

```csharp
// Create the InteractiveBrowserCredential using details
// from app registered in the Azure AD for US Government portal
var credential = new InteractiveBrowserCredential(
    "YOUR_TENANT_ID",
    "YOUR_CLIENT_ID",
    new InteractiveBrowserCredentialOptions
    {
        // https://login.microsoftonline.us
        AuthorityHost = AzureAuthorityHosts.AzureGovernment,
        RedirectUri = new Uri("YOUR_REDIRECT_URI"),
    });

// Create the authentication provider
var authProvider = new AzureIdentityAuthenticationProvider(
    credential,
    isCaeEnabled: true,
    scopes: ["https://graph.microsoft.us/.default"]);

// Create the Microsoft Graph client object using
// the Microsoft Graph for US Government L4 endpoint
// NOTE: The API version must be included in the URL
var graphClient = new GraphServiceClient(
    authProvider,
    "https://graph.microsoft.us/v1.0");
```

Go

Copy

```go
import (
    "github.com/Azure/azure-sdk-for-go/sdk/azcore/cloud"
    "github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
    "github.com/Azure/azure-sdk-for-go/sdk/azidentity"
    graph "github.com/microsoftgraph/msgraph-sdk-go"
    auth "github.com/microsoftgraph/msgraph-sdk-go-core/authentication"
)
```

Go

Copy

```go
// Create the InteractiveBrowserCredential using details
// from app registered in the Azure AD for US Government portal
credential, _ := azidentity.NewInteractiveBrowserCredential(
    &azidentity.InteractiveBrowserCredentialOptions{
        ClientID: "YOUR_CLIENT_ID",
        TenantID: "YOUR_TENANT_ID",
        ClientOptions: policy.ClientOptions{
            // https://login.microsoftonline.us
            Cloud: cloud.AzureGovernment,
        },
        RedirectURL: "YOUR_REDIRECT_URL",
    })

// Create the authentication provider
authProvider, _ := auth.NewAzureIdentityAuthenticationProviderWithScopes(credential,
    []string{"https://graph.microsoft.us/.default"})

// Create a request adapter using the auth provider
adapter, _ := graph.NewGraphRequestAdapter(authProvider)

// Set the service root to the
// Microsoft Graph for US Government L4 endpoint
// NOTE: The API version must be included in the URL
adapter.SetBaseUrl("https://graph.microsoft.us/v1.0")

// Create a Graph client using request adapter
graphClient := graph.NewGraphServiceClient(adapter)
```

Java

Copy

```java
// Create the InteractiveBrowserCredential using details
// from app registered in the Azure AD for US Government portal
final InteractiveBrowserCredential credential = new InteractiveBrowserCredentialBuilder()
    .clientId("YOUR_CLIENT_ID").tenantId("YOUR_TENANT_ID")
    // https://login.microsoftonline.us
    .authorityHost(AzureAuthorityHosts.AZURE_GOVERNMENT)
    .redirectUrl("YOUR_REDIRECT_URI").build();

final String[] scopes = new String[] {"https://graph.microsoft.us/.default"};

// Create the authentication provider
if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
// Set the service root to the
// Microsoft Graph for US Government L4 endpoint
// NOTE: The API version must be included in the URL
graphClient.getRequestAdapter().setBaseUrl("https://graph.microsoft.us/v1.0");
```

PHP

Copy

```php
$scopes = ['https://graph.microsoft.us/.default'];

// Create the Microsoft Graph client object using
// the Microsoft Graph for US Government L4 endpoint
// $tokenRequestContext is one of the token context classes
// from Microsoft\Kiota\Authentication\Oauth
$graphClient = new GraphServiceClient($tokenRequestContext, $scopes, NationalCloud::US_GOV);
```

PowerShell

Copy

```powershell
Connect-MgGraph -Environment USGov -ClientId 'YOUR_CLIENT_ID' `
  -TenantId 'YOUR_TENANT_ID' -Scopes 'https://graph.microsoft.us/.default'
```

Python

Copy

```python
scopes = ['https://graph.microsoft.us/.default']

credential = InteractiveBrowserCredential(
    tenant_id='YOUR_TENANT_ID',
    client_id='YOUR_CLIENT_ID',
    redirect_uri='YOUR_REDIRECT_URI')

auth_provider = AzureIdentityAuthenticationProvider(credential, scopes=scopes)

# Create the HTTP client using
# the Microsoft Graph for US Government L4 endpoint
http_client = GraphClientFactory.create_with_default_middleware(
    host=NationalClouds.US_GOV)

adapter = GraphRequestAdapter(auth_provider, http_client)

graph_client = GraphServiceClient(request_adapter=adapter)
```

TypeScript

Copy

```typescript
// Create the InteractiveBrowserCredential using details
// from app registered in the Azure AD for US Government portal
const credential = new InteractiveBrowserCredential({
  clientId: 'YOUR_CLIENT_ID',
  tenantId: 'YOUR_TENANT_ID',
  // https://login.microsoftonline.us
  authorityHost: AzureAuthorityHosts.AzureGovernment,
  redirectUri: 'YOUR_REDIRECT_URI',
});

// Create the authentication provider
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ['https://graph.microsoft.us/.default'],
});

// Create the Microsoft Graph client object using
// the Microsoft Graph for US Government L4 endpoint
// NOTE: Do not include the version in the baseUrl
const graphClient = Client.initWithMiddleware({
  authProvider: authProvider,
  baseUrl: 'https://graph.microsoft.us',
});
```

* * *
