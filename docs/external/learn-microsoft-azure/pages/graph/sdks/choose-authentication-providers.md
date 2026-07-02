# Choose a Microsoft Graph authentication provider based on the scenario

Authentication providers implement the code required to acquire a token using the Microsoft Authentication Library (MSAL), handle some potential errors for cases like incremental consent, expired passwords, and conditional access, and then set the HTTP request authorization header. The following table lists the providers that match the scenarios for different [application types](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-app-types).

| Scenario | Flow/Grant | Audience | Provider |
| --- | --- | --- | --- |
| [Single Page App](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-spa-acquire-token) | Authorization Code with PKCE | Delegated Consumer/Org | [Authorization code provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#authorization-code-provider) |
| [Web App that calls web APIs](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-web-app-call-api-acquire-token) |  |  |  |
|  | Authorization Code | Delegated Consumer/Org | [Authorization code provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#authorization-code-provider) |
|  | Client Credentials | App Only | [Client credentials provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#client-credentials-provider) |
| [Web API that calls web APIs](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-web-api-call-api-acquire-token) |  |  |  |
|  | On Behalf Of | Delegated Consumer/Org | [On-behalf-of provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#on-behalf-of-provider) |
|  | Client Credentials | App Only | [Client credentials provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#client-credentials-provider) |
| [Desktop app that calls web APIs](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-desktop-acquire-token) |  |  |  |
|  | Interactive | Delegated Consumer/Org | [Interactive provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#interactive-provider) |
|  | Integrated Windows | Delegated Org | [Integrated Windows provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#integrated-windows-provider) |
|  | Resource Owner | Delegated Org | [Username/password provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#usernamepassword-provider) |
|  | Device Code | Delegated Org | [Device code provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#device-code-provider) |
| [Daemon app](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-daemon-acquire-token) |  |  |  |
|  | Client Credentials | App Only | [Client credentials provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#client-credentials-provider) |
| [Mobile app that calls web APIs](https://learn.microsoft.com/en-us/azure/active-directory/develop/scenario-mobile-acquire-token) |  |  |  |
|  | Interactive | Delegated Consumer/Org | [Interactive provider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#interactive-provider) |

The following code snippets were written with the latest versions of their respective SDKs. If you encounter compiler errors with these snippets, make sure you have the latest versions. The following Azure Identity libraries provide the authentication providers used:

- .NET developers need to add the [Azure.Identity](https://learn.microsoft.com/en-us/dotnet/api/azure.identity) package.
- TypeScript and JavaScript developers need to add the [@azure/identity](https://learn.microsoft.com/en-us/javascript/api/@azure/identity) library.
- Java and Android developers need to add the [azure-identity](https://learn.microsoft.com/en-us/java/api/overview/azure/identity-readme) library.

## Authorization code provider

The authorization code flow enables native and web apps to obtain tokens in the user's name securely. To learn more, see [Microsoft identity platform and OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow).

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_1_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_1_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_1_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_1_typescript)

C#

Copy

```csharp
var scopes = new[] { "User.Read" };

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
var tenantId = "common";

// Values from app registration
var clientId = "YOUR_CLIENT_ID";
var clientSecret = "YOUR_CLIENT_SECRET";

// For authorization code flow, the user signs into the Microsoft
// identity platform, and the browser is redirected back to your app
// with an authorization code in the query parameters
var authorizationCode = "AUTH_CODE_FROM_REDIRECT";

// using Azure.Identity;
var options = new AuthorizationCodeCredentialOptions
{
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
};

// https://learn.microsoft.com/dotnet/api/azure.identity.authorizationcodecredential
var authCodeCredential = new AuthorizationCodeCredential(
    tenantId, clientId, clientSecret, authorizationCode, options);

var graphClient = new GraphServiceClient(authCodeCredential, scopes);
```

The [Azure Identity Client Module for Go](https://pkg.go.dev/github.com/Azure/azure-sdk-for-go/sdk/azidentity) doesn't support the authorization code flow.

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID"; // or "common" for multi-tenant apps
final String clientSecret = "YOUR_CLIENT_SECRET";
final String authorizationCode = "AUTH_CODE_FROM_REDIRECT";
final String redirectUrl = "YOUR_REDIRECT_URI";
final String[] scopes = new String[] { "User.Read" };

final AuthorizationCodeCredential credential = new AuthorizationCodeCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).clientSecret(clientSecret)
    .authorizationCode(authorizationCode).redirectUrl(redirectUrl).build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

The Microsoft Graph PHP SDK doesn't use MSAL libraries but custom authentication. In this case, [AuthorizationCodeContext()](https://github.com/microsoft/kiota-authentication-phpleague-php/blob/dev/src/Oauth/AuthorizationCodeContext.php).

PHP

Copy

```php
$scopes = ['User.Read'];

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
$tenantId = 'common';

// Values from app registration
$clientId = 'YOUR_CLIENT_ID';
$clientSecret = 'YOUR_CLIENT_SECRET';
$redirectUri = 'YOUR_REDIRECT_URI';

// For authorization code flow, the user signs into the Microsoft
// identity platform, and the browser is redirected back to your app
// with an authorization code in the query parameters
$authorizationCode = 'AUTH_CODE_FROM_REDIRECT';

// Microsoft\Kiota\Authentication\Oauth\AuthorizationCodeContext
$tokenContext = new AuthorizationCodeContext(
    $tenantId,
    $clientId,
    $clientSecret,
    $authorizationCode,
    $redirectUri);

$graphClient = new GraphServiceClient($tokenContext, $scopes);
```

In the following example, we're using the asynchronous [AuthorizationCodeCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio.authorizationcodecredential?view=azure-python&preserve-view=true). You can alternatively use the [synchronous version](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.authorizationcodecredential?view=azure-python&preserve-view=true) of this credential.

Python

Copy

```python
scopes = ['User.Read']

# Multi-tenant apps can use "common",
# single-tenant apps must use the tenant ID from the Azure portal
tenant_id = 'common'

# Values from app registration
client_id = 'YOUR_CLIENT_ID'
client_secret = 'YOUR_CLIENT_SECRET'
redirect_uri = 'YOUR_REDIRECT_URI'

# For authorization code flow, the user signs into the Microsoft
# identity platform, and the browser is redirected back to your app
# with an authorization code in the query parameters
authorization_code = 'AUTH_CODE_FROM_REDIRECT'

# azure.identity.aio
credential = AuthorizationCodeCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    authorization_code=authorization_code,
    redirect_uri=redirect_uri,
    client_secret=client_secret)

graph_client = GraphServiceClient(credential, scopes) # type: ignore
```

### Using @azure/MSAL-browser for browser applications

TypeScript

Copy

```typescript
// @azure/msal-browser
const pca = new PublicClientApplication({
  auth: {
    clientId: 'YOUR_CLIENT_ID',
    authority: `https://login.microsoft.online/${'YOUR_TENANT_ID'}`,
    redirectUri: 'YOUR_REDIRECT_URI',
  },
});

// Authenticate to get the user's account
const authResult = await pca.acquireTokenPopup({
  scopes: ['User.Read'],
});

if (!authResult.account) {
  throw new Error('Could not authenticate');
}

// @microsoft/microsoft-graph-client/authProviders/authCodeMsalBrowser
const authProvider = new AuthCodeMSALBrowserAuthenticationProvider(pca, {
  account: authResult.account,
  interactionType: InteractionType.Popup,
  scopes: ['User.Read'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

### Using @azure/identity for server-side applications

TypeScript

Copy

```typescript
// @azure/identity
const credential = new AuthorizationCodeCredential(
  'YOUR_TENANT_ID',
  'YOUR_CLIENT_ID',
  'YOUR_CLIENT_SECRET',
  'AUTHORIZATION_CODE',
  'REDIRECT_URL',
);

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ['User.Read'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

## Client credentials provider

The client credential flow enables service applications to run without user interaction. Access is based on the identity of the application. For more information, see [Microsoft identity platform and the OAuth 2.0 client credentials flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow).

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_2_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_2_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_2_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_2_typescript)

### Using a client certificate

C#

Copy

```csharp
var scopes = new[] { "https://graph.microsoft.com/.default" };

// Values from app registration
var clientId = "YOUR_CLIENT_ID";
var tenantId = "YOUR_TENANT_ID";
var clientCertificate = X509CertificateLoader
    .LoadCertificateFromFile("MyCertificate.pfx");

// using Azure.Identity;
var options = new ClientCertificateCredentialOptions
{
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
};

// https://learn.microsoft.com/dotnet/api/azure.identity.clientcertificatecredential
var clientCertCredential = new ClientCertificateCredential(
    tenantId, clientId, clientCertificate, options);

var graphClient = new GraphServiceClient(clientCertCredential, scopes);
```

### Using a client secret

C#

Copy

```csharp
// The client credentials flow requires that you request the
// /.default scope, and pre-configure your permissions on the
// app registration in Azure. An administrator must grant consent
// to those permissions beforehand.
var scopes = new[] { "https://graph.microsoft.com/.default" };

// Values from app registration
var clientId = "YOUR_CLIENT_ID";
var tenantId = "YOUR_TENANT_ID";
var clientSecret = "YOUR_CLIENT_SECRET";

// using Azure.Identity;
var options = new ClientSecretCredentialOptions
{
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
};

// https://learn.microsoft.com/dotnet/api/azure.identity.clientsecretcredential
var clientSecretCredential = new ClientSecretCredential(
    tenantId, clientId, clientSecret, options);

var graphClient = new GraphServiceClient(clientSecretCredential, scopes);
```

### Using a client certificate

Go

Copy

```go
// Load certificate
certFile, _ := os.Open("certificate.pem")
info, _ := certFile.Stat()
certBytes := make([]byte, info.Size())
certFile.Read(certBytes)
certFile.Close()

certs, key, _ := azidentity.ParseCertificates(certBytes, nil)

cred, _ := azidentity.NewClientCertificateCredential(
    "TENANT_ID",
    "CLIENT_ID",
    certs,
    key,
    nil,
)

graphClient, _ := graph.NewGraphServiceClientWithCredentials(
    cred, []string{"https://graph.microsoft.com/.default"})
```

### Using a client secret

Go

Copy

```go
cred, _ := azidentity.NewClientSecretCredential(
    "TENANT_ID",
    "CLIENT_ID",
    "CLIENT_SECRET",
    nil,
)

graphClient, _ := graph.NewGraphServiceClientWithCredentials(
    cred, []string{"https://graph.microsoft.com/.default"})
```

### Using a client certificate

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID";
final String clientCertificatePath = "MyCertificate.pem";

// The client credentials flow requires that you request the
// /.default scope, and pre-configure your permissions on the
// app registration in Azure. An administrator must grant consent
// to those permissions beforehand.
final String[] scopes = new String[] {"https://graph.microsoft.com/.default"};

final ClientCertificateCredential credential = new ClientCertificateCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).pemCertificate(clientCertificatePath)
    .build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

### Using a client secret

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID";
final String clientSecret = "YOUR_CLIENT_SECRET";

// The client credentials flow requires that you request the
// /.default scope, and pre-configure your permissions on the
// app registration in Azure. An administrator must grant consent
// to those permissions beforehand.
final String[] scopes = new String[] { "https://graph.microsoft.com/.default" };

final ClientSecretCredential credential = new ClientSecretCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).clientSecret(clientSecret).build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

The Microsoft Graph PHP SDK doesn't use MSAL libraries but custom authentication. In this case, [ClientCredentialContext()](https://github.com/microsoft/kiota-authentication-phpleague-php/blob/dev/src/Oauth/ClientCredentialContext.php).

### Using a client certificate

PHP

Copy

```php
// The client credentials flow requires that you request the
// /.default scope, and pre-configure your permissions on the
// app registration in Azure. An administrator must grant consent
// to those permissions beforehand.
$scopes = ['https://graph.microsoft.com/.default'];

// Values from app registration
$clientId = 'YOUR_CLIENT_ID';
$tenantId = 'YOUR_TENANT_ID';

// Certificate details
$certificatePath = 'PATH_TO_CERTIFICATE';
$privateKeyPath = 'PATH_TO_PRIVATE_KEY';
$privateKeyPassphrase = 'PASSPHRASE';

// Microsoft\Kiota\Authentication\Oauth\ClientCredentialCertificateContext
$tokenContext = new ClientCredentialCertificateContext(
    $tenantId,
    $clientId,
    $certificatePath,
    $privateKeyPath,
    $privateKeyPassphrase);

$graphClient = new GraphServiceClient($tokenContext, $scopes);
```

### Using a client secret

PHP

Copy

```php
// The client credentials flow requires that you request the
// /.default scope, and pre-configure your permissions on the
// app registration in Azure. An administrator must grant consent
// to those permissions beforehand.
$scopes = ['https://graph.microsoft.com/.default'];

// Values from app registration
$clientId = 'YOUR_CLIENT_ID';
$tenantId = 'YOUR_TENANT_ID';
$clientSecret = 'YOUR_CLIENT_SECRET';

// Microsoft\Kiota\Authentication\Oauth\ClientCredentialContext
$tokenContext = new ClientCredentialContext(
    $tenantId,
    $clientId,
    $clientSecret);

$graphClient = new GraphServiceClient($tokenContext, $scopes);
```

### Using a client certificate

In the following example, we're using the asynchronous [CertificateCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio.certificatecredential?view=azure-python&preserve-view=true). You can alternatively use the [synchronous version](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.certificatecredential?view=azure-python&preserve-view=true) of this credential.

Python

Copy

```python
# The client credentials flow requires that you request the
# /.default scope, and pre-configure your permissions on the
# app registration in Azure. An administrator must grant consent
# to those permissions beforehand.
scopes = ['https://graph.microsoft.com/.default']

# Values from app registration
tenant_id = 'YOUR_TENANT_ID'
client_id = 'YOUR_CLIENT_ID'
certificate_path = 'YOUR_CERTIFICATE_PATH'

# azure.identity.aio
credential = CertificateCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    certificate_path=certificate_path)

graph_client = GraphServiceClient(credential, scopes) # type: ignore
```

### Using a client secret

In the following example, we're using the asynchronous [ClientSecretCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio.clientsecretcredential?view=azure-python&preserve-view=true). You can alternatively use the [synchronous version](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential?view=azure-python&preserve-view=true) of this credential.

Python

Copy

```python
# The client credentials flow requires that you request the
# /.default scope, and pre-configure your permissions on the
# app registration in Azure. An administrator must grant consent
# to those permissions beforehand.
scopes = ['https://graph.microsoft.com/.default']

# Values from app registration
tenant_id = 'YOUR_TENANT_ID'
client_id = 'YOUR_CLIENT_ID'
client_secret = 'YOUR_CLIENT_SECRET'

# azure.identity.aio
credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret)

graph_client = GraphServiceClient(credential, scopes) # type: ignore
```

### Using a client certificate

TypeScript

Copy

```typescript
// @azure/identity
const credential = new ClientCertificateCredential(
  'YOUR_TENANT_ID',
  'YOUR_CLIENT_ID',
  'YOUR_CERTIFICATE_PATH',
);

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  // The client credentials flow requires that you request the
  // /.default scope, and pre-configure your permissions on the
  // app registration in Azure. An administrator must grant consent
  // to those permissions beforehand.
  scopes: ['https://graph.microsoft.com/.default'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

### Using a client's secret

TypeScript

Copy

```typescript
// @azure/identity
const credential = new ClientSecretCredential(
  'YOUR_TENANT_ID',
  'YOUR_CLIENT_ID',
  'YOUR_CLIENT_SECRET',
);

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  // The client credentials flow requires that you request the
  // /.default scope, and pre-configure your permissions on the
  // app registration in Azure. An administrator must grant consent
  // to those permissions beforehand.
  scopes: ['https://graph.microsoft.com/.default'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

## On-behalf-of provider

The on-behalf-of flow is applicable when your application calls a service/web API, which calls the Microsoft Graph API. Learn more by reading [Microsoft identity platform and OAuth 2.0 On-Behalf-Of flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-on-behalf-of-flow)

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_3_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_3_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_3_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_3_typescript)

C#

Copy

```csharp
var scopes = new[] { "https://graph.microsoft.com/.default" };

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
var tenantId = "common";

// Values from app registration
var clientId = "YOUR_CLIENT_ID";
var clientSecret = "YOUR_CLIENT_SECRET";

// using Azure.Identity;
var options = new OnBehalfOfCredentialOptions
{
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
};

// This is the incoming token to exchange using on-behalf-of flow
var oboToken = "JWT_TOKEN_TO_EXCHANGE";

var onBehalfOfCredential = new OnBehalfOfCredential(
    tenantId, clientId, clientSecret, oboToken, options);

var graphClient = new GraphServiceClient(onBehalfOfCredential, scopes);
```

Go

Copy

```go
cred, _ := azidentity.NewOnBehalfOfCredentialWithSecret(
    "TENANT_ID",
    "CLIENT_ID",
    "USER_ASSERTION_STRING",
    "CLIENT_SECRET",
    nil,
)

graphClient, _ := graph.NewGraphServiceClientWithCredentials(
    cred, []string{"https://graph.microsoft.com/.default"})
```

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID"; // or "common" for multi-tenant apps
final String clientSecret = "YOUR_CLIENT_SECRET";
final String[] scopes = new String[] {"https://graph.microsoft.com/.default"};

// This is the incoming token to exchange using on-behalf-of flow
final String oboToken = "JWT_TOKEN_TO_EXCHANGE";

final OnBehalfOfCredential credential = new OnBehalfOfCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).clientSecret(clientSecret)
    .userAssertion(oboToken).build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

The Microsoft Graph PHP SDK doesn't use MSAL libraries but custom authentication. In this case, [OnBehalfOfContext()](https://github.com/microsoft/kiota-authentication-phpleague-php/blob/dev/src/Oauth/OnBehalfOfContext.php).

PHP

Copy

```php
$scopes = ['https://graph.microsoft.com/.default'];

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
$tenantId = 'common';

// Values from app registration
$clientId = 'YOUR_CLIENT_ID';
$clientSecret = 'YOUR_CLIENT_SECRET';

// This is the incoming token to exchange using on-behalf-of flow
$oboToken = 'JWT_TOKEN_TO_EXCHANGE';

// Microsoft\Kiota\Authentication\Oauth\OnBehalfOfContext
$tokenContext = new OnBehalfOfContext(
    $tenantId,
    $clientId,
    $clientSecret,
    $oboToken);

$graphClient = new GraphServiceClient($tokenContext, $scopes);
```

In the following example, we're using the asynchronous [OnBehalfOfCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.aio.onbehalfofcredential?view=azure-python&preserve-view=true). You can alternatively use the [synchronous version](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.onbehalfofcredential?view=azure-python&preserve-view=true) of this credential.

Python

Copy

```python
scopes = ['https://graph.microsoft.com/.default']

# Multi-tenant apps can use "common",
# single-tenant apps must use the tenant ID from the Azure portal
tenant_id = 'common'

# Values from app registration
client_id = 'YOUR_CLIENT_ID'
client_secret = 'YOUR_CLIENT_SECRET'

# This is the incoming token to exchange using on-behalf-of flow
obo_token = 'JWT_TOKEN_TO_EXCHANGE'

# azure.identity.aio
credential = OnBehalfOfCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret,
    user_assertion=obo_token)

graph_client = GraphServiceClient(credential, scopes) # type: ignore
```

TypeScript

Copy

```typescript
// @azure/identity
const credential = new OnBehalfOfCredential({
  tenantId: 'YOUR_TENANT_ID',
  clientId: 'YOUR_CLIENT_ID',
  clientSecret: 'YOUR_CLIENT_SECRET',
  userAssertionToken: 'JWT_TOKEN_TO_EXCHANGE',
});

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ['https://graph.microsoft.com/.default'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

## Implicit provider

Implicit Authentication flow isn't recommended due to its [disadvantages](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps-04#section-9.8.6). Public clients such as native apps and single-page apps should now use the authorization code flow with the PKCE extension instead. [Reference](https://oauth.net/2/grant-types/implicit/).

## Device code provider

The device code flow enables sign-in to devices through another device. For details, see [Microsoft identity platform and the OAuth 2.0 device code flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-device-code).

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_4_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_4_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_4_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_4_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_4_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_4_typescript)

C#

Copy

```csharp
var scopes = new[] { "User.Read" };

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
var tenantId = "common";

// Value from app registration
var clientId = "YOUR_CLIENT_ID";

// using Azure.Identity;
var options = new DeviceCodeCredentialOptions
{
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
    ClientId = clientId,
    TenantId = tenantId,
    // Callback function that receives the user prompt
    // Prompt contains the generated device code that user must
    // enter during the auth process in the browser
    DeviceCodeCallback = (code, cancellation) =>
    {
        Console.WriteLine(code.Message);
        return Task.FromResult(0);
    },
};

// https://learn.microsoft.com/dotnet/api/azure.identity.devicecodecredential
var deviceCodeCredential = new DeviceCodeCredential(options);

var graphClient = new GraphServiceClient(deviceCodeCredential, scopes);
```

Go

Copy

```go
cred, _ := azidentity.NewDeviceCodeCredential(&azidentity.DeviceCodeCredentialOptions{
    TenantID: "TENANT_ID",
    ClientID: "CLIENT_ID",
    UserPrompt: func(ctx context.Context, message azidentity.DeviceCodeMessage) error {
        fmt.Println(message.Message)
        return nil
    },
})

graphClient, _ := graph.NewGraphServiceClientWithCredentials(
    cred, []string{"User.Read"})
```

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID"; // or "common" for multi-tenant apps
final String[] scopes = new String[] {"User.Read"};

final DeviceCodeCredential credential = new DeviceCodeCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).challengeConsumer(challenge -> {
        // Display challenge to the user
        System.out.println(challenge.getMessage());
    }).build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

The Microsoft Graph PHP SDK doesn't use MSAL libraries but custom authentication. To authenticate, use one of the following contexts: [AuthorizationCodeContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#authorization-code-provider), [ClientCredentialContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#client-credentials-provider), [OnBehalfOfContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#on-behalf-of-provider).

Python

Copy

```python
scopes = ['User.Read']

# Multi-tenant apps can use "common",
# single-tenant apps must use the tenant ID from the Azure portal
tenant_id = 'common'

# Values from app registration
client_id = 'YOUR_CLIENT_ID'

# azure.identity
credential = DeviceCodeCredential(
    tenant_id=tenant_id,
    client_id=client_id)

graph_client = GraphServiceClient(credential, scopes)
```

TypeScript

Copy

```typescript
// @azure/identity
const credential = new DeviceCodeCredential({
  tenantId: 'YOUR_TENANT_ID',
  clientId: 'YOUR_CLIENT_ID',
  userPromptCallback: (info) => {
    console.log(info.message);
  },
});

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ['User.Read'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

## Integrated Windows provider

The integrated Windows flow allows Windows computers to use the Web Account Manager (WAM) to acquire an access token when domain-joined silently.

Authentication through WAM has specific requirements. See [Azure Identity Brokered Authentication client library for .NET](https://github.com/Azure/azure-sdk-for-net/tree/main/sdk/identity/Azure.Identity.Broker) for details.

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_5_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_5_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_5_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_5_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_5_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_5_typescript)

C#

Copy

```csharp
[DllImport("user32.dll")]
static extern IntPtr GetForegroundWindow();

// Get parent window handle
var parentWindowHandle = GetForegroundWindow();

var scopes = new[] { "User.Read" };

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
var tenantId = "common";

// Value from app registration
var clientId = "YOUR_CLIENT_ID";

// using Azure.Identity.Broker;
// This will use the Web Account Manager in Windows
var options = new InteractiveBrowserCredentialBrokerOptions(parentWindowHandle)
{
    ClientId = clientId,
    TenantId = tenantId,
};

// https://learn.microsoft.com/dotnet/api/azure.identity.interactivebrowsercredential
var credential = new InteractiveBrowserCredential(options);

var graphClient = new GraphServiceClient(credential, scopes);

return graphClient;
```

Not applicable.

Not applicable.

Not applicable.

Not applicable.

Not applicable.

## Interactive provider

The interactive flow is used by mobile applications (Xamarin and UWP) and desktop applications to call Microsoft Graph in the name of a user. For details, see [Acquiring tokens interactively](https://github.com/AzureAD/microsoft-authentication-library-for-dotnet/wiki/Acquiring-tokens-interactively).

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_6_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_6_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_6_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_6_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_6_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_6_typescript)

C#

Copy

```csharp
var scopes = new[] { "User.Read" };

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
var tenantId = "common";

// Value from app registration
var clientId = "YOUR_CLIENT_ID";

// using Azure.Identity;
var options = new InteractiveBrowserCredentialOptions
{
    TenantId = tenantId,
    ClientId = clientId,
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
    // MUST be http://localhost or http://localhost:PORT
    // See https://github.com/AzureAD/microsoft-authentication-library-for-dotnet/wiki/System-Browser-on-.Net-Core
    RedirectUri = new Uri("http://localhost"),
};

// https://learn.microsoft.com/dotnet/api/azure.identity.interactivebrowsercredential
var interactiveCredential = new InteractiveBrowserCredential(options);

var graphClient = new GraphServiceClient(interactiveCredential, scopes);
```

Go

Copy

```go
cred, _ := azidentity.NewInteractiveBrowserCredential(&azidentity.InteractiveBrowserCredentialOptions{
    TenantID:    "TENANT_ID",
    ClientID:    "CLIENT_ID",
    RedirectURL: "REDIRECT_URL",
})

graphClient, _ := graph.NewGraphServiceClientWithCredentials(
    cred, []string{"User.Read"})
```

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID"; // or "common" for multi-tenant apps
final String redirectUrl = "YOUR_REDIRECT_URI";
final String[] scopes = new String[] {"User.Read"};

final InteractiveBrowserCredential credential = new InteractiveBrowserCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).redirectUrl(redirectUrl).build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

The Microsoft Graph PHP SDK doesn't use MSAL libraries but custom authentication. To authenticate, use one of the following contexts: [AuthorizationCodeContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#authorization-code-provider), [ClientCredentialContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#client-credentials-provider), [OnBehalfOfContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#on-behalf-of-provider).

Python

Copy

```python
scopes = ['User.Read']

# Multi-tenant apps can use "common",
# single-tenant apps must use the tenant ID from the Azure portal
tenant_id = 'common'

# Values from app registration
client_id = 'YOUR_CLIENT_ID'
redirect_uri = 'http://localhost:8000'

# azure.identity
credential = InteractiveBrowserCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    redirect_uri=redirect_uri)

graph_client = GraphServiceClient(credential, scopes)
```

TypeScript

Copy

```typescript
// @azure/identity
const credential = new InteractiveBrowserCredential({
  tenantId: 'YOUR_TENANT_ID',
  clientId: 'YOUR_CLIENT_ID',
  redirectUri: 'http://localhost',
});

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ['User.Read'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

## Username/password provider

The username/password provider allows an application to sign in a user using their username and password.

Microsoft recommends that you use the most secure authentication flow available. The authentication flow described in this procedure requires a very high degree of trust in the application, and carries risks that are not present in other flows. You should only use this flow when other more secure flows, such as managed identities, aren't viable. For more information, see [Microsoft identity platform and the OAuth 2.0 resource owner password credential](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth-ropc).

- [C#](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_7_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_7_go)
- [Java](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_7_java)
- [PHP](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_7_PHP)
- [Python](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_7_python)
- [TypeScript](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#tabpanel_7_typescript)

C#

Copy

```csharp
var scopes = new[] { "User.Read" };

// Multi-tenant apps can use "common",
// single-tenant apps must use the tenant ID from the Azure portal
var tenantId = "common";

// Value from app registration
var clientId = "YOUR_CLIENT_ID";

// using Azure.Identity;
var options = new UsernamePasswordCredentialOptions
{
    AuthorityHost = AzureAuthorityHosts.AzurePublicCloud,
};

var userName = "adelev@contoso.com";
var password = "Password1!";

// https://learn.microsoft.com/dotnet/api/azure.identity.usernamepasswordcredential
var userNamePasswordCredential = new UsernamePasswordCredential(
    userName, password, tenantId, clientId, options);

var graphClient = new GraphServiceClient(userNamePasswordCredential, scopes);
```

Go

Copy

```go
cred, _ := azidentity.NewUsernamePasswordCredential(
    "TENANT_ID",
    "CLIENT_ID",
    "USER_NAME",
    "PASSWORD",
    nil,
)

graphClient, _ := graph.NewGraphServiceClientWithCredentials(
    cred, []string{"User.Read"})
```

Java

Copy

```java
final String clientId = "YOUR_CLIENT_ID";
final String tenantId = "YOUR_TENANT_ID"; // or "common" for multi-tenant apps
final String userName = "YOUR_USER_NAME";
final String password = "YOUR_PASSWORD";
final String[] scopes = new String[] {"User.Read"};

final UsernamePasswordCredential credential = new UsernamePasswordCredentialBuilder()
    .clientId(clientId).tenantId(tenantId).username(userName).password(password)
    .build();

if (null == scopes || null == credential) {
    throw new Exception("Unexpected error");
}

final GraphServiceClient graphClient = new GraphServiceClient(credential, scopes);
```

The Microsoft Graph PHP SDK doesn't use MSAL libraries but custom authentication. To authenticate, use one of the following contexts: [AuthorizationCodeContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#authorization-code-provider), [ClientCredentialContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#client-credentials-provider), [OnBehalfOfContext()](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers?tabs=csharp#on-behalf-of-provider).

Python

Copy

```python
scopes = ['User.Read']

# Multi-tenant apps can use "common",
# single-tenant apps must use the tenant ID from the Azure portal
tenant_id = 'common'

# Values from app registration
client_id = 'YOUR_CLIENT_ID'

# User name and password
username = 'adelev@contoso.com'
password = 'Password1!'

# azure.identity
credential = UsernamePasswordCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    username=username,
    password=password)

graph_client = GraphServiceClient(credential, scopes)
```

TypeScript

Copy

```typescript
// @azure/identity
const credential = new UsernamePasswordCredential(
  'YOUR_TENANT_ID',
  'YOUR_CLIENT_ID',
  'YOUR_USER_NAME',
  'YOUR_PASSWORD',
);

// @microsoft/microsoft-graph-client/authProviders/azureTokenCredentials
const authProvider = new TokenCredentialAuthenticationProvider(credential, {
  scopes: ['User.Read'],
});

const graphClient = Client.initWithMiddleware({ authProvider: authProvider });
```

## Next steps

- For code samples that show you how to use the Microsoft identity platform to secure different application types, see [Microsoft identity platform code samples (v2.0 endpoint)](https://learn.microsoft.com/en-us/azure/active-directory/develop/sample-v2-code).
- Authentication providers require a client ID. You'll want to [register your application](https://entra.microsoft.com/) after you set up your authentication provider.
- Let us know if a required OAuth flow isn't currently supported by voting for or opening a [Microsoft Graph feature request](https://aka.ms/graphrequests).

* * *
