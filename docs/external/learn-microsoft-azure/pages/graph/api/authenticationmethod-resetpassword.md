# authenticationMethod: resetPassword

Namespace: microsoft.graph

Reset a user's password, represented by a [password authentication method](https://learn.microsoft.com/en-us/graph/api/resources/passwordauthenticationmethod?view=graph-rest-1.0) object. This can only be done by an administrator with appropriate permissions and can't be performed on a user's own account.

To reset a user's password in Azure AD B2C, use the [Update user](https://learn.microsoft.com/en-us/graph/api/user-update?view=graph-rest-1.0) API operation and update the **passwordProfile** \> **forceChangePasswordNextSignIn** object.

This flow writes the new password to Microsoft Entra ID and pushes it to on-premises Active Directory if configured using password writeback. The admin can either provide a new password or have the system generate one. The user is prompted to change their password on their next sign in.

This reset is a long-running operation and returns a **Location** header with a link where the caller can periodically check for the status of the reset operation.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ❌ |

## Permissions

Choose the permission or permissions marked as least privileged for this API. Use a higher privileged permission or permissions [only if your app requires it](https://learn.microsoft.com/en-us/graph/permissions-overview#best-practices-for-using-microsoft-graph-permissions). For details about delegated and application permissions, see [Permission types](https://learn.microsoft.com/en-us/graph/permissions-overview#permission-types). To learn more about these permissions, see the [permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Least privileged permissions | Higher privileged permissions |
| --- | --- | --- |
| Delegated (work or school account) | UserAuthenticationMethod.ReadWrite.All | Not available. |
| Delegated (personal Microsoft account) | Not supported. | Not supported. |
| Application | Not supported. | Not supported. |

Important

For delegated access using work or school accounts, the signed-in user must be assigned a supported [Microsoft Entra role](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/permissions-reference?toc=%2Fgraph%2Ftoc.json) or a custom role that grants the permissions required for this operation. This operation supports the following built-in roles, which provide only the least privilege necessary:

- Authentication Administrator
- Privileged Authentication Administrator

When users manage their own authentication methods, the system prompts them to complete multi-factor authentication (MFA) if they last authenticated more than 10 minutes ago in the current session.

Admins with _User Administrator_, _Helpdesk Administrator_, or _Password Administrator_ roles can also reset passwords for non-admin users and a limited set of admin roles as defined in [Who can reset passwords](https://learn.microsoft.com/en-us/azure/active-directory/roles/privileged-roles-permissions#who-can-reset-passwords).

## HTTP request

The ID of the password authentication method, referenced by `{passwordMethods-id}`, is always `28c10230-6103-485e-b985-444c60001490`.

HTTP

Copy

```http
POST /users/{id | userPrincipalName}/authentication/methods/{passwordMethods-id}/resetPassword
```

## Request headers

| Name | Description |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Content-type | application/json. Required. |

## Request body

In the request body, provide a JSON object with the following parameters.

| Parameter | Type | Description |
| --- | --- | --- |
| newPassword | String | The new password. Required for tenants with hybrid password scenarios. If omitted for a cloud-only password, the system returns a system-generated password. This is a unicode string with no other encoding. It's validated against the tenant's banned password system before acceptance, and must adhere to the tenant's cloud and/or on-premises password requirements. |

## Response

If the caller provided a password in the request body, this method returns a `202 Accepted` response code and no response body. The response might also include a **Location** header with a URL to check the status of the [reset operation](https://learn.microsoft.com/en-us/graph/api/longrunningoperation-get?view=graph-rest-1.0).

If the caller used the system-generated password option, this method returns a `202 Accepted` response code and a [passwordResetResponse](https://learn.microsoft.com/en-us/graph/api/resources/passwordresetresponse?view=graph-rest-1.0) object in the response body which contains a Microsoft-generated password. The response might also include a **Location** header with a URL to check the status of the [reset operation](https://learn.microsoft.com/en-us/graph/api/longrunningoperation-get?view=graph-rest-1.0).

### Response headers

| Name | Description |
| --- | --- |
| Location | URL to call to check the status of the operation. Required. |
| Retry-after | Duration in seconds. Optional. |

## Examples

### Example 1: User-submitted password

The following example shows how to call this API when the caller submits a password.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/users/6ea91a8d-e32e-41a1-b7bd-d2d185eed0e0/authentication/methods/28c10230-6103-485e-b985-444c60001490/resetPassword
Content-type: application/json

{
    "newPassword": "Cuyo5459"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Users.Item.Authentication.Methods.Item.ResetPassword;

var requestBody = new ResetPasswordPostRequestBody
{
	NewPassword = "Cuyo5459",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Users["{user-id}"].Authentication.Methods["{authenticationMethod-id}"].ResetPassword.PostAsync(requestBody);
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
	  graphusers "github.com/microsoftgraph/msgraph-sdk-go/users"
	  //other-imports
)

requestBody := graphusers.NewResetPasswordPostRequestBody()
newPassword := "Cuyo5459"
requestBody.SetNewPassword(&newPassword)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
resetPassword, err := graphClient.Users().ByUserId("user-id").Authentication().Methods().ByAuthenticationMethodId("authenticationMethod-id").ResetPassword().Post(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.users.item.authentication.methods.item.resetpassword.ResetPasswordPostRequestBody resetPasswordPostRequestBody = new com.microsoft.graph.users.item.authentication.methods.item.resetpassword.ResetPasswordPostRequestBody();
resetPasswordPostRequestBody.setNewPassword("Cuyo5459");
var result = graphClient.users().byUserId("{user-id}").authentication().methods().byAuthenticationMethodId("{authenticationMethod-id}").resetPassword().post(resetPasswordPostRequestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const passwordResetResponse = {
    newPassword: 'Cuyo5459'
};

await client.api('/users/6ea91a8d-e32e-41a1-b7bd-d2d185eed0e0/authentication/methods/28c10230-6103-485e-b985-444c60001490/resetPassword')
	.post(passwordResetResponse);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Users\Item\Authentication\Methods\Item\ResetPassword\ResetPasswordPostRequestBody;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ResetPasswordPostRequestBody();
$requestBody->setNewPassword('Cuyo5459');

$result = $graphServiceClient->users()->byUserId('user-id')->authentication()->methods()->byAuthenticationMethodId('authenticationMethod-id')->resetPassword()->post($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.SignIns

$params = @{
	newPassword = "Cuyo5459"
}

Reset-MgUserAuthenticationMethodPassword -UserId $userId -AuthenticationMethodId $authenticationMethodId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.users.item.authentication.methods.item.reset_password.reset_password_post_request_body import ResetPasswordPostRequestBody
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ResetPasswordPostRequestBody(
	new_password = "Cuyo5459",
)

result = await graph_client.users.by_user_id('user-id').authentication.methods.by_authentication_method_id('authenticationMethod-id').reset_password.post(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response.

HTTP

Copy

```http
HTTP/1.1 202 Accepted
Content-type: application/json
Location: https://graph.microsoft.com/v1.0/users/6ea91a8d-e32e-41a1-b7bd-d2d185eed0e0/authentication/operations/88e7560c-9ebf-435c-8089-c3998ac1ec51?aadgdc=DUB02P&aadgsu=ssprprod-a
```

### Example 2: System-generated password

The following example shows how to call this API when the caller doesn't submit a password.

#### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/authenticationmethod-resetpassword?view=graph-rest-1.0&tabs=http#tabpanel_2_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/users/6ea91a8d-e32e-41a1-b7bd-d2d185eed0e0/authentication/methods/28c10230-6103-485e-b985-444c60001490/resetPassword

{

}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Users.Item.Authentication.Methods.Item.ResetPassword;

var requestBody = new ResetPasswordPostRequestBody
{
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Users["{user-id}"].Authentication.Methods["{authenticationMethod-id}"].ResetPassword.PostAsync(requestBody);
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
	  graphusers "github.com/microsoftgraph/msgraph-sdk-go/users"
	  //other-imports
)

requestBody := graphusers.NewResetPasswordPostRequestBody()

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
resetPassword, err := graphClient.Users().ByUserId("user-id").Authentication().Methods().ByAuthenticationMethodId("authenticationMethod-id").ResetPassword().Post(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.users.item.authentication.methods.item.resetpassword.ResetPasswordPostRequestBody resetPasswordPostRequestBody = new com.microsoft.graph.users.item.authentication.methods.item.resetpassword.ResetPasswordPostRequestBody();
var result = graphClient.users().byUserId("{user-id}").authentication().methods().byAuthenticationMethodId("{authenticationMethod-id}").resetPassword().post(resetPasswordPostRequestBody);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const passwordResetResponse = {

};

await client.api('/users/6ea91a8d-e32e-41a1-b7bd-d2d185eed0e0/authentication/methods/28c10230-6103-485e-b985-444c60001490/resetPassword')
	.post(passwordResetResponse);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Users\Item\Authentication\Methods\Item\ResetPassword\ResetPasswordPostRequestBody;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ResetPasswordPostRequestBody();

$result = $graphServiceClient->users()->byUserId('user-id')->authentication()->methods()->byAuthenticationMethodId('authenticationMethod-id')->resetPassword()->post($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.SignIns

$params = @{
}

Reset-MgUserAuthenticationMethodPassword -UserId $userId -AuthenticationMethodId $authenticationMethodId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.users.item.authentication.methods.item.reset_password.reset_password_post_request_body import ResetPasswordPostRequestBody
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ResetPasswordPostRequestBody(
)

result = await graph_client.users.by_user_id('user-id').authentication.methods.by_authentication_method_id('authenticationMethod-id').reset_password.post(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

#### Response

The following example shows the response. You can use the ID in the **Location** header to check the status of the operation via the [long-running operation API](https://learn.microsoft.com/en-us/graph/api/longrunningoperation-get?view=graph-rest-1.0).

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 202 Accepted
Location: https://graph.microsoft.com/v1.0/users/6ea91a8d-e32e-41a1-b7bd-d2d185eed0e0/authentication/operations/77bafe36-3ac0-4f89-96e4-a4a5a48da851?aadgdc=DUB02P&aadgsu=ssprprod-a
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#microsoft.graph.passwordResetResponse",
    "newPassword": "Cuyo5459"
}
```

* * *
