# Configure SAML-based single sign-on for your application using Microsoft Graph

Single sign-on (SSO) is an authentication method that allows users to sign in to one application and then access multiple applications without needing to sign in again. Microsoft Entra supports various SSO methods, including OpenID Connect, OAuth, Security Assertion Markup Language (SAML), password-based, and linked SSO. Using Microsoft Graph, you can automate the configuration of SSO for your application.

In this tutorial, you learn how to:

- Identify SAML-based apps in the Microsoft Entra gallery and configure SAML-based SSO for an app
- Add app roles to an application and grant them to users
- Configure claims to emit in the SAML token
- Configure a certificate for federated SSO
- Retrieve the Microsoft Entra ID SAML metadata for your application that you use to complete the integration

The steps for setting up SAML applications apply to configurations that use the SP-initiated flow.
The IDP-initiated flow requires modifying the SAML application in Entra ID to add the identifier (entity ID).

## Prerequisites

This tutorial configures SSO for the AWS IAM Identity Center. However, most of the steps on Microsoft Graph apply to any other app that you want to configure SSO.

- Sign in to an API client such as [Graph Explorer](https://aka.ms/ge) with the privileges to instantiate apps from the Microsoft Entra application gallery, configure app roles, and policies on apps. _Cloud Application Administrator_ in the least privileged Microsoft Entra built-in role with these permissions.
- Grant yourself the following delegated permissions: `Application.ReadWrite.All`, `AppRoleAssignment.ReadWrite.All`, `Policy.Read.All`, `Policy.ReadWrite.ApplicationConfiguration`, and `User.ReadWrite.All`.
- Have a test user to assign to the application. You'll create a matching user in the AWS IAM Identity Center later in this tutorial.

## Step 1: Identify the application to configure

To create an app that supports SSO, you register it through the Microsoft Entra App Gallery. The Microsoft Entra App Gallery is a catalog of thousands of preintegrated apps that simplify deploying and configuring SSO and automated user provisioning. In Microsoft Graph, this list is available through the **applicationTemplate** entity.

In this step, you identify the application template for the `AWS IAM Identity Center (successor to AWS Single Sign-On)` application that you want to configure. Record its **id**.

### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_1_python)

msgraph

CopyTry It

```msgraph
GET https://graph.microsoft.com/v1.0/applicationTemplates?$filter=displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ApplicationTemplates.GetAsync((requestConfiguration) =>
{
	requestConfiguration.QueryParameters.Filter = "displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'";
});
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplicationtemplates "github.com/microsoftgraph/msgraph-sdk-go/applicationtemplates"
	  //other-imports
)

requestFilter := "displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'"

requestParameters := &graphapplicationtemplates.ApplicationTemplatesRequestBuilderGetQueryParameters{
	Filter: &requestFilter,
}
configuration := &graphapplicationtemplates.ApplicationTemplatesRequestBuilderGetRequestConfiguration{
	QueryParameters: requestParameters,
}

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
applicationTemplates, err := graphClient.ApplicationTemplates().Get(context.Background(), configuration)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ApplicationTemplateCollectionResponse result = graphClient.applicationTemplates().get(requestConfiguration -> {
	requestConfiguration.queryParameters.filter = "displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'";
});
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

let applicationTemplates = await client.api('/applicationTemplates')
	.filter('displayName eq \'AWS IAM Identity Center (successor to AWS Single Sign-On)\'')
	.get();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\ApplicationTemplates\ApplicationTemplatesRequestBuilderGetRequestConfiguration;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestConfiguration = new ApplicationTemplatesRequestBuilderGetRequestConfiguration();
$queryParameters = ApplicationTemplatesRequestBuilderGetRequestConfiguration::createQueryParameters();
$queryParameters->filter = "displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'";
$requestConfiguration->queryParameters = $queryParameters;

$result = $graphServiceClient->applicationTemplates()->get($requestConfiguration)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Get-MgApplicationTemplate -Filter "displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'"
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.application_templates.application_templates_request_builder import ApplicationTemplatesRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
query_params = ApplicationTemplatesRequestBuilder.ApplicationTemplatesRequestBuilderGetQueryParameters(
		filter = "displayName eq 'AWS IAM Identity Center (successor to AWS Single Sign-On)'",
)

request_configuration = RequestConfiguration(
query_parameters = query_params,
)

result = await graph_client.application_templates.get(request_configuration = request_configuration)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#applicationTemplates",
    "@microsoft.graph.tips": "Use $select to choose only the properties your app needs, as this can lead to performance improvements. For example: GET applicationTemplates?$select=categories,description",
    "value": [\
        {\
            "id": "21ed01d2-ec13-4e9e-86c1-cd546719ebc4",\
            "displayName": "AWS IAM Identity Center (successor to AWS Single Sign-On)",\
            "homePageUrl": "https://aws.amazon.com/",\
            "supportedSingleSignOnModes": [\
                "saml",\
                "external"\
            ],\
            "supportedProvisioningTypes": [\
                "sync"\
            ],\
            "logoUrl": "https://galleryapplogos1.azureedge.net/app-logo/awssinglesignon_FC86917E_215.png",\
            "categories": [\
                "developerServices",\
                "itInfrastructure",\
                "security",\
                "New"\
            ],\
            "publisher": "Amazon Web Services, Inc.",\
            "description": "Federate once to AWS IAM Identity Center (successor to AWS Single Sign-On) & use it to centrally manage access to multiple AWS accounts and IAM Identity Center enabled apps. Provision users via SCIM."\
        }\
    ]
}
```

## Step 2: Instantiate the application

Using the **id** value for the application template, create an instance of the application in your tenant. Here, you name the application **AWS Contoso**. The response includes an application and service principal object for **AWS Contoso**, which is an instance of the **AWS IAM Identity Center (successor to AWS Single Sign-On)** app. Record the IDs of the created application and service principal objects for use later in this tutorial.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_2_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/applicationTemplates/21ed01d2-ec13-4e9e-86c1-cd546719ebc4/instantiate
Content-type: application/json

{
  "displayName": "AWS Contoso"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.ApplicationTemplates.Item.Instantiate;

var requestBody = new InstantiatePostRequestBody
{
	DisplayName = "AWS Contoso",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ApplicationTemplates["{applicationTemplate-id}"].Instantiate.PostAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphapplicationtemplates "github.com/microsoftgraph/msgraph-sdk-go/applicationtemplates"
	  //other-imports
)

requestBody := graphapplicationtemplates.NewInstantiatePostRequestBody()
displayName := "AWS Contoso"
requestBody.SetDisplayName(&displayName)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
instantiate, err := graphClient.ApplicationTemplates().ByApplicationTemplateId("applicationTemplate-id").Instantiate().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.applicationtemplates.item.instantiate.InstantiatePostRequestBody instantiatePostRequestBody = new com.microsoft.graph.applicationtemplates.item.instantiate.InstantiatePostRequestBody();
instantiatePostRequestBody.setDisplayName("AWS Contoso");
var result = graphClient.applicationTemplates().byApplicationTemplateId("{applicationTemplate-id}").instantiate().post(instantiatePostRequestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const applicationServicePrincipal = {
  displayName: 'AWS Contoso'
};

await client.api('/applicationTemplates/21ed01d2-ec13-4e9e-86c1-cd546719ebc4/instantiate')
	.post(applicationServicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\ApplicationTemplates\Item\Instantiate\InstantiatePostRequestBody;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new InstantiatePostRequestBody();
$requestBody->setDisplayName('AWS Contoso');

$result = $graphServiceClient->applicationTemplates()->byApplicationTemplateId('applicationTemplate-id')->instantiate()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	displayName = "AWS Contoso"
}

Invoke-MgInstantiateApplicationTemplate -ApplicationTemplateId $applicationTemplateId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.applicationtemplates.item.instantiate.instantiate_post_request_body import InstantiatePostRequestBody
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = InstantiatePostRequestBody(
	display_name = "AWS Contoso",
)

result = await graph_client.application_templates.by_application_template_id('applicationTemplate-id').instantiate.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#microsoft.graph.applicationServicePrincipal",
    "application": {
        "id": "b7308000-8bb3-467b-bfc7-8dbbfd759ad9",
        "appId": "2fbc8259-0f56-4f56-9870-93a228020936",
        "applicationTemplateId": "21ed01d2-ec13-4e9e-86c1-cd546719ebc4",
        "createdDateTime": "2024-02-21T17:14:33Z",
        "deletedDateTime": null,
        "displayName": "AWS Contoso",
        "description": null,
        "groupMembershipClaims": null,
        "identifierUris": [],
        "isFallbackPublicClient": false,
        "signInAudience": "AzureADMyOrg",
        "tags": [],
        "tokenEncryptionKeyId": null,
        "defaultRedirectUri": null,
        "samlMetadataUrl": null,
        "optionalClaims": null,
        "addIns": [],
        "api": {
            "acceptMappedClaims": null,
            "knownClientApplications": [],
            "requestedAccessTokenVersion": null,
            "oauth2PermissionScopes": [\
                {\
                    "adminConsentDescription": "Allow the application to access AWS Contoso on behalf of the signed-in user.",\
                    "adminConsentDisplayName": "Access AWS Contoso",\
                    "id": "f5419931-094d-481d-b801-ab3ed60d48d8",\
                    "isEnabled": true,\
                    "type": "User",\
                    "userConsentDescription": "Allow the application to access AWS Contoso on your behalf.",\
                    "userConsentDisplayName": "Access AWS Contoso",\
                    "value": "user_impersonation"\
                }\
            ],
            "preAuthorizedApplications": []
        },
        "appRoles": [\
            {\
                "allowedMemberTypes": [\
                    "User"\
                ],\
                "displayName": "User",\
                "id": "8774f594-1d59-4279-b9d9-59ef09a23530",\
                "isEnabled": true,\
                "description": "User",\
                "value": null,\
                "origin": "Application"\
            },\
            {\
                "allowedMemberTypes": [\
                    "User"\
                ],\
                "displayName": "msiam_access",\
                "id": "e7f1a7f3-9eda-48e0-9963-bd67bf531afd",\
                "isEnabled": true,\
                "description": "msiam_access",\
                "value": null,\
                "origin": "Application"\
            }\
        ],
        "info": {
            "logoUrl": null,
            "marketingUrl": null,
            "privacyStatementUrl": null,
            "supportUrl": null,
            "termsOfServiceUrl": null
        },
        "keyCredentials": [],
        "parentalControlSettings": {
            "countriesBlockedForMinors": [],
            "legalAgeGroupRule": "Allow"
        },
        "passwordCredentials": [],
        "publicClient": {
            "redirectUris": []
        },
        "requiredResourceAccess": [],
        "verifiedPublisher": {
            "displayName": null,
            "verifiedPublisherId": null,
            "addedDateTime": null
        },
        "web": {
            "homePageUrl": "https://*.signin.aws.amazon.com/platform/saml/acs/*?metadata=awssinglesignon|ISV9.1|primary|z",
            "redirectUris": [\
                "https://*.signin.aws.amazon.com/platform/saml/acs/*"\
            ],
            "logoutUrl": null
        }
    },
    "servicePrincipal": {
        "id": "d3616293-fff8-4415-9f01-33b05dad1b46",
        "deletedDateTime": null,
        "accountEnabled": true,
        "appId": "2fbc8259-0f56-4f56-9870-93a228020936",
        "applicationTemplateId": "21ed01d2-ec13-4e9e-86c1-cd546719ebc4",
        "appDisplayName": "AWS Contoso",
        "alternativeNames": [],
        "appOwnerOrganizationId": "38d49456-54d4-455d-a8d6-c383c71e0a6d",
        "displayName": "AWS Contoso",
        "appRoleAssignmentRequired": true,
        "loginUrl": null,
        "logoutUrl": null,
        "homepage": "https://*.signin.aws.amazon.com/platform/saml/acs/*?metadata=awssinglesignon|ISV9.1|primary|z",
        "notificationEmailAddresses": [],
        "preferredSingleSignOnMode": null,
        "preferredTokenSigningKeyThumbprint": null,
        "replyUrls": [],
        "servicePrincipalNames": [\
            "2fbc8259-0f56-4f56-9870-93a228020936"\
        ],
        "servicePrincipalType": "Application",
        "tags": [\
            "WindowsAzureActiveDirectoryIntegratedApp"\
        ],
        "tokenEncryptionKeyId": null,
        "samlSingleSignOnSettings": null,
        "addIns": [],
        "appRoles": [\
            {\
                "allowedMemberTypes": [\
                    "User"\
                ],\
                "displayName": "User",\
                "id": "8774f594-1d59-4279-b9d9-59ef09a23530",\
                "isEnabled": true,\
                "description": "User",\
                "value": null,\
                "origin": "Application"\
            },\
            {\
                "allowedMemberTypes": [\
                    "User"\
                ],\
                "displayName": "msiam_access",\
                "id": "e7f1a7f3-9eda-48e0-9963-bd67bf531afd",\
                "isEnabled": true,\
                "description": "msiam_access",\
                "value": null,\
                "origin": "Application"\
            }\
        ],
        "info": {
            "logoUrl": null,
            "marketingUrl": null,
            "privacyStatementUrl": null,
            "supportUrl": null,
            "termsOfServiceUrl": null
        },
        "keyCredentials": [],
        "oauth2PermissionScopes": [\
            {\
                "adminConsentDescription": "Allow the application to access AWS Contoso on behalf of the signed-in user.",\
                "adminConsentDisplayName": "Access AWS Contoso",\
                "id": "f5419931-094d-481d-b801-ab3ed60d48d8",\
                "isEnabled": true,\
                "type": "User",\
                "userConsentDescription": "Allow the application to access AWS Contoso on your behalf.",\
                "userConsentDisplayName": "Access AWS Contoso",\
                "value": "user_impersonation"\
            }\
        ],
        "passwordCredentials": [],
        "verifiedPublisher": {
            "displayName": null,
            "verifiedPublisherId": null,
            "addedDateTime": null
        }
    }
}
```

## Step 3: Configure single sign-on

In this step, you configure SSO for both the AWS Contoso. For the application, you configure the SAML URLs while for the service principal, you set the SSO mode to `saml`.

### Step 3.1: Set single sign-on mode for the service principal

Set `saml` as the SSO mode for the AWS Contoso service principal. The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_3_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46
Content-type: application/json

{
  "preferredSingleSignOnMode": "saml"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ServicePrincipal
{
	PreferredSingleSignOnMode = "saml",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].PatchAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewServicePrincipal()
preferredSingleSignOnMode := "saml"
requestBody.SetPreferredSingleSignOnMode(&preferredSingleSignOnMode)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
servicePrincipals, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ServicePrincipal servicePrincipal = new ServicePrincipal();
servicePrincipal.setPreferredSingleSignOnMode("saml");
ServicePrincipal result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").patch(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const servicePrincipal = {
  preferredSingleSignOnMode: 'saml'
};

await client.api('/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46')
	.update(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ServicePrincipal;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ServicePrincipal();
$requestBody->setPreferredSingleSignOnMode('saml');

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	preferredSingleSignOnMode = "saml"
}

Update-MgServicePrincipal -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.service_principal import ServicePrincipal
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ServicePrincipal(
	preferred_single_sign_on_mode = "saml",
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Step 3.2: Set basic SAML URLs for the application

Set the **web**/ **redirectUris** and **web**/ **redirectUris** for the AWS Contoso application. The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_4_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/applications/b7308000-8bb3-467b-bfc7-8dbbfd759ad9
Content-type: application/json

{
    "identifierUris": [\
        "https://signin.aws.amazon.com/saml"\
    ],
    "web": {
        "redirectUris": [\
            "https://signin.aws.amazon.com/saml"\
        ]
    }
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new Application
{
	IdentifierUris = new List<string>
	{
		"https://signin.aws.amazon.com/saml",
	},
	Web = new WebApplication
	{
		RedirectUris = new List<string>
		{
			"https://signin.aws.amazon.com/saml",
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Applications["{application-id}"].PatchAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewApplication()
identifierUris := []string {
	"https://signin.aws.amazon.com/saml",
}
requestBody.SetIdentifierUris(identifierUris)
web := graphmodels.NewWebApplication()
redirectUris := []string {
	"https://signin.aws.amazon.com/saml",
}
web.SetRedirectUris(redirectUris)
requestBody.SetWeb(web)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
applications, err := graphClient.Applications().ByApplicationId("application-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

Application application = new Application();
LinkedList<String> identifierUris = new LinkedList<String>();
identifierUris.add("https://signin.aws.amazon.com/saml");
application.setIdentifierUris(identifierUris);
WebApplication web = new WebApplication();
LinkedList<String> redirectUris = new LinkedList<String>();
redirectUris.add("https://signin.aws.amazon.com/saml");
web.setRedirectUris(redirectUris);
application.setWeb(web);
Application result = graphClient.applications().byApplicationId("{application-id}").patch(application);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const application = {
    identifierUris: [\
        'https://signin.aws.amazon.com/saml'\
    ],
    web: {
        redirectUris: [\
            'https://signin.aws.amazon.com/saml'\
        ]
    }
};

await client.api('/applications/b7308000-8bb3-467b-bfc7-8dbbfd759ad9')
	.update(application);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\Application;
use Microsoft\Graph\Generated\Models\WebApplication;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new Application();
$requestBody->setIdentifierUris(['https://signin.aws.amazon.com/saml', 	]);
$web = new WebApplication();
$web->setRedirectUris(['https://signin.aws.amazon.com/saml', 	]);
$requestBody->setWeb($web);

$result = $graphServiceClient->applications()->byApplicationId('application-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	identifierUris = @(
	"https://signin.aws.amazon.com/saml"
)
web = @{
	redirectUris = @(
	"https://signin.aws.amazon.com/saml"
)
}
}

Update-MgApplication -ApplicationId $applicationId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.application import Application
from msgraph.generated.models.web_application import WebApplication
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = Application(
	identifier_uris = [\
		"https://signin.aws.amazon.com/saml",\
	],
	web = WebApplication(
		redirect_uris = [\
			"https://signin.aws.amazon.com/saml",\
		],
	),
)

result = await graph_client.applications.by_application_id('application-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Step 4: Add app roles

If the application requires the role information in the token, add the definition of the roles in the **appRoles** property. AWS Contoso was instantiated with the default `User` and `msiam_access` roles - don't modify or remove them. To add more roles, you include both the existing roles and the new roles in the **appRoles** object in the request, otherwise, the existing roles are replaced.

In this step, add the `Finance,WAAD` and `Admin,WAAD` roles to the AWS Contoso service principal. The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_5_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46
Content-type: application/json

{
    "appRoles": [\
        {\
            "allowedMemberTypes": [\
                "User"\
            ],\
            "description": "User",\
            "displayName": "User",\
            "id": "8774f594-1d59-4279-b9d9-59ef09a23530",\
            "isEnabled": true,\
            "origin": "Application",\
            "value": null\
        },\
        {\
            "allowedMemberTypes": [\
                "User"\
            ],\
            "description": "msiam_access",\
            "displayName": "msiam_access",\
            "id": "e7f1a7f3-9eda-48e0-9963-bd67bf531afd",\
            "isEnabled": true,\
            "origin": "Application",\
            "value": null\
        },\
        {\
            "allowedMemberTypes": [\
                "User"\
            ],\
            "description": "Admin,WAAD",\
            "displayName": "Admin,WAAD",\
            "id": "3a84e31e-bffa-470f-b9e6-754a61e4dc63",\
            "isEnabled": true,\
            "value": "arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD"\
        },\
        {\
            "allowedMemberTypes": [\
                "User"\
            ],\
            "description": "Finance,WAAD",\
            "displayName": "Finance,WAAD",\
            "id": "7a960000-ded3-455b-8c04-4f2ace00319b",\
            "isEnabled": true,\
            "value": "arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD"\
        }\
    ]
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ServicePrincipal
{
	AppRoles = new List<AppRole>
	{
		new AppRole
		{
			AllowedMemberTypes = new List<string>
			{
				"User",
			},
			Description = "User",
			DisplayName = "User",
			Id = Guid.Parse("8774f594-1d59-4279-b9d9-59ef09a23530"),
			IsEnabled = true,
			Origin = "Application",
			Value = null,
		},
		new AppRole
		{
			AllowedMemberTypes = new List<string>
			{
				"User",
			},
			Description = "msiam_access",
			DisplayName = "msiam_access",
			Id = Guid.Parse("e7f1a7f3-9eda-48e0-9963-bd67bf531afd"),
			IsEnabled = true,
			Origin = "Application",
			Value = null,
		},
		new AppRole
		{
			AllowedMemberTypes = new List<string>
			{
				"User",
			},
			Description = "Admin,WAAD",
			DisplayName = "Admin,WAAD",
			Id = Guid.Parse("3a84e31e-bffa-470f-b9e6-754a61e4dc63"),
			IsEnabled = true,
			Value = "arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD",
		},
		new AppRole
		{
			AllowedMemberTypes = new List<string>
			{
				"User",
			},
			Description = "Finance,WAAD",
			DisplayName = "Finance,WAAD",
			Id = Guid.Parse("7a960000-ded3-455b-8c04-4f2ace00319b"),
			IsEnabled = true,
			Value = "arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD",
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].PatchAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewServicePrincipal()

appRole := graphmodels.NewAppRole()
allowedMemberTypes := []string {
	"User",
}
appRole.SetAllowedMemberTypes(allowedMemberTypes)
description := "User"
appRole.SetDescription(&description)
displayName := "User"
appRole.SetDisplayName(&displayName)
id := uuid.MustParse("8774f594-1d59-4279-b9d9-59ef09a23530")
appRole.SetId(&id)
isEnabled := true
appRole.SetIsEnabled(&isEnabled)
origin := "Application"
appRole.SetOrigin(&origin)
value := null
appRole.SetValue(&value)
appRole1 := graphmodels.NewAppRole()
allowedMemberTypes := []string {
	"User",
}
appRole1.SetAllowedMemberTypes(allowedMemberTypes)
description := "msiam_access"
appRole1.SetDescription(&description)
displayName := "msiam_access"
appRole1.SetDisplayName(&displayName)
id := uuid.MustParse("e7f1a7f3-9eda-48e0-9963-bd67bf531afd")
appRole1.SetId(&id)
isEnabled := true
appRole1.SetIsEnabled(&isEnabled)
origin := "Application"
appRole1.SetOrigin(&origin)
value := null
appRole1.SetValue(&value)
appRole2 := graphmodels.NewAppRole()
allowedMemberTypes := []string {
	"User",
}
appRole2.SetAllowedMemberTypes(allowedMemberTypes)
description := "Admin,WAAD"
appRole2.SetDescription(&description)
displayName := "Admin,WAAD"
appRole2.SetDisplayName(&displayName)
id := uuid.MustParse("3a84e31e-bffa-470f-b9e6-754a61e4dc63")
appRole2.SetId(&id)
isEnabled := true
appRole2.SetIsEnabled(&isEnabled)
value := "arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD"
appRole2.SetValue(&value)
appRole3 := graphmodels.NewAppRole()
allowedMemberTypes := []string {
	"User",
}
appRole3.SetAllowedMemberTypes(allowedMemberTypes)
description := "Finance,WAAD"
appRole3.SetDescription(&description)
displayName := "Finance,WAAD"
appRole3.SetDisplayName(&displayName)
id := uuid.MustParse("7a960000-ded3-455b-8c04-4f2ace00319b")
appRole3.SetId(&id)
isEnabled := true
appRole3.SetIsEnabled(&isEnabled)
value := "arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD"
appRole3.SetValue(&value)

appRoles := []graphmodels.AppRoleable {
	appRole,
	appRole1,
	appRole2,
	appRole3,
}
requestBody.SetAppRoles(appRoles)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
servicePrincipals, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ServicePrincipal servicePrincipal = new ServicePrincipal();
LinkedList<AppRole> appRoles = new LinkedList<AppRole>();
AppRole appRole = new AppRole();
LinkedList<String> allowedMemberTypes = new LinkedList<String>();
allowedMemberTypes.add("User");
appRole.setAllowedMemberTypes(allowedMemberTypes);
appRole.setDescription("User");
appRole.setDisplayName("User");
appRole.setId(UUID.fromString("8774f594-1d59-4279-b9d9-59ef09a23530"));
appRole.setIsEnabled(true);
appRole.setOrigin("Application");
appRole.setValue(null);
appRoles.add(appRole);
AppRole appRole1 = new AppRole();
LinkedList<String> allowedMemberTypes1 = new LinkedList<String>();
allowedMemberTypes1.add("User");
appRole1.setAllowedMemberTypes(allowedMemberTypes1);
appRole1.setDescription("msiam_access");
appRole1.setDisplayName("msiam_access");
appRole1.setId(UUID.fromString("e7f1a7f3-9eda-48e0-9963-bd67bf531afd"));
appRole1.setIsEnabled(true);
appRole1.setOrigin("Application");
appRole1.setValue(null);
appRoles.add(appRole1);
AppRole appRole2 = new AppRole();
LinkedList<String> allowedMemberTypes2 = new LinkedList<String>();
allowedMemberTypes2.add("User");
appRole2.setAllowedMemberTypes(allowedMemberTypes2);
appRole2.setDescription("Admin,WAAD");
appRole2.setDisplayName("Admin,WAAD");
appRole2.setId(UUID.fromString("3a84e31e-bffa-470f-b9e6-754a61e4dc63"));
appRole2.setIsEnabled(true);
appRole2.setValue("arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD");
appRoles.add(appRole2);
AppRole appRole3 = new AppRole();
LinkedList<String> allowedMemberTypes3 = new LinkedList<String>();
allowedMemberTypes3.add("User");
appRole3.setAllowedMemberTypes(allowedMemberTypes3);
appRole3.setDescription("Finance,WAAD");
appRole3.setDisplayName("Finance,WAAD");
appRole3.setId(UUID.fromString("7a960000-ded3-455b-8c04-4f2ace00319b"));
appRole3.setIsEnabled(true);
appRole3.setValue("arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD");
appRoles.add(appRole3);
servicePrincipal.setAppRoles(appRoles);
ServicePrincipal result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").patch(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const servicePrincipal = {
    appRoles: [\
        {\
            allowedMemberTypes: [\
                'User'\
            ],\
            description: 'User',\
            displayName: 'User',\
            id: '8774f594-1d59-4279-b9d9-59ef09a23530',\
            isEnabled: true,\
            origin: 'Application',\
            value: null\
        },\
        {\
            allowedMemberTypes: [\
                'User'\
            ],\
            description: 'msiam_access',\
            displayName: 'msiam_access',\
            id: 'e7f1a7f3-9eda-48e0-9963-bd67bf531afd',\
            isEnabled: true,\
            origin: 'Application',\
            value: null\
        },\
        {\
            allowedMemberTypes: [\
                'User'\
            ],\
            description: 'Admin,WAAD',\
            displayName: 'Admin,WAAD',\
            id: '3a84e31e-bffa-470f-b9e6-754a61e4dc63',\
            isEnabled: true,\
            value: 'arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD'\
        },\
        {\
            allowedMemberTypes: [\
                'User'\
            ],\
            description: 'Finance,WAAD',\
            displayName: 'Finance,WAAD',\
            id: '7a960000-ded3-455b-8c04-4f2ace00319b',\
            isEnabled: true,\
            value: 'arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD'\
        }\
    ]
};

await client.api('/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46')
	.update(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ServicePrincipal;
use Microsoft\Graph\Generated\Models\AppRole;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ServicePrincipal();
$appRolesAppRole1 = new AppRole();
$appRolesAppRole1->setAllowedMemberTypes(['User', 	]);
$appRolesAppRole1->setDescription('User');
$appRolesAppRole1->setDisplayName('User');
$appRolesAppRole1->setId('8774f594-1d59-4279-b9d9-59ef09a23530');
$appRolesAppRole1->setIsEnabled(true);
$appRolesAppRole1->setOrigin('Application');
$appRolesAppRole1->setValue(null);
$appRolesArray []= $appRolesAppRole1;
$appRolesAppRole2 = new AppRole();
$appRolesAppRole2->setAllowedMemberTypes(['User', 	]);
$appRolesAppRole2->setDescription('msiam_access');
$appRolesAppRole2->setDisplayName('msiam_access');
$appRolesAppRole2->setId('e7f1a7f3-9eda-48e0-9963-bd67bf531afd');
$appRolesAppRole2->setIsEnabled(true);
$appRolesAppRole2->setOrigin('Application');
$appRolesAppRole2->setValue(null);
$appRolesArray []= $appRolesAppRole2;
$appRolesAppRole3 = new AppRole();
$appRolesAppRole3->setAllowedMemberTypes(['User', 	]);
$appRolesAppRole3->setDescription('Admin,WAAD');
$appRolesAppRole3->setDisplayName('Admin,WAAD');
$appRolesAppRole3->setId('3a84e31e-bffa-470f-b9e6-754a61e4dc63');
$appRolesAppRole3->setIsEnabled(true);
$appRolesAppRole3->setValue('arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD');
$appRolesArray []= $appRolesAppRole3;
$appRolesAppRole4 = new AppRole();
$appRolesAppRole4->setAllowedMemberTypes(['User', 	]);
$appRolesAppRole4->setDescription('Finance,WAAD');
$appRolesAppRole4->setDisplayName('Finance,WAAD');
$appRolesAppRole4->setId('7a960000-ded3-455b-8c04-4f2ace00319b');
$appRolesAppRole4->setIsEnabled(true);
$appRolesAppRole4->setValue('arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD');
$appRolesArray []= $appRolesAppRole4;
$requestBody->setAppRoles($appRolesArray);

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	appRoles = @(
		@{
			allowedMemberTypes = @(
			"User"
		)
		description = "User"
		displayName = "User"
		id = "8774f594-1d59-4279-b9d9-59ef09a23530"
		isEnabled = $true
		origin = "Application"
		value = $null
	}
	@{
		allowedMemberTypes = @(
		"User"
	)
	description = "msiam_access"
	displayName = "msiam_access"
	id = "e7f1a7f3-9eda-48e0-9963-bd67bf531afd"
	isEnabled = $true
	origin = "Application"
	value = $null
}
@{
	allowedMemberTypes = @(
	"User"
)
description = "Admin,WAAD"
displayName = "Admin,WAAD"
id = "3a84e31e-bffa-470f-b9e6-754a61e4dc63"
isEnabled = $true
value = "arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD"
}
@{
allowedMemberTypes = @(
"User"
)
description = "Finance,WAAD"
displayName = "Finance,WAAD"
id = "7a960000-ded3-455b-8c04-4f2ace00319b"
isEnabled = $true
value = "arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD"
}
)
}

Update-MgServicePrincipal -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.service_principal import ServicePrincipal
from msgraph.generated.models.app_role import AppRole
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ServicePrincipal(
	app_roles = [\
		AppRole(\
			allowed_member_types = [\
				"User",\
			],\
			description = "User",\
			display_name = "User",\
			id = UUID("8774f594-1d59-4279-b9d9-59ef09a23530"),\
			is_enabled = True,\
			origin = "Application",\
			value = None,\
		),\
		AppRole(\
			allowed_member_types = [\
				"User",\
			],\
			description = "msiam_access",\
			display_name = "msiam_access",\
			id = UUID("e7f1a7f3-9eda-48e0-9963-bd67bf531afd"),\
			is_enabled = True,\
			origin = "Application",\
			value = None,\
		),\
		AppRole(\
			allowed_member_types = [\
				"User",\
			],\
			description = "Admin,WAAD",\
			display_name = "Admin,WAAD",\
			id = UUID("3a84e31e-bffa-470f-b9e6-754a61e4dc63"),\
			is_enabled = True,\
			value = "arn:aws:iam::212743507312:role/accountname-aws-admin,arn:aws:iam::212743507312:saml-provider/WAAD",\
		),\
		AppRole(\
			allowed_member_types = [\
				"User",\
			],\
			description = "Finance,WAAD",\
			display_name = "Finance,WAAD",\
			id = UUID("7a960000-ded3-455b-8c04-4f2ace00319b"),\
			is_enabled = True,\
			value = "arn:aws:iam::212743507312:role/accountname-aws-finance,arn:aws:iam::212743507312:saml-provider/WAAD",\
		),\
	],
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Step 5: Configure claims mapping

You want to configure the SAML attributes by mapping the Microsoft Entra ID fields with specific AWS IAM Identity Center application attributes. You therefore create a claims mapping policy and assign it to the service principal.

### Step 5.1: Create a claims mapping policy

In addition to the basic claims, configure the following claims for Microsoft Entra ID to emit in the SAML token:

| Claim name | Source |
| --- | --- |
| `https://aws.amazon.com/SAML/Attributes/Role` | `assignedroles` |
| `https://aws.amazon.com/SAML/Attributes/RoleSessionName` | `userprincipalname` |
| `https://aws.amazon.com/SAML/Attributes/SessionDuration` | `"900"` |
| `appRoles` | `assignedroles` |
| `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier` | `userprincipalname` |

Some keys in the claims mapping policy, such as **Version**, are case sensitive. The error message "Property has an invalid value" indicates a case sensitivity issue.

Create the claims mapping policy and record its ID for use later in this tutorial.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_6_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies
Content-type: application/json

{
    "definition": [\
        "{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}"\
    ],
    "displayName": "AWS Claims Policy",
    "isOrganizationDefault": false
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ClaimsMappingPolicy
{
	Definition = new List<string>
	{
		"{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}",
	},
	DisplayName = "AWS Claims Policy",
	IsOrganizationDefault = false,
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Policies.ClaimsMappingPolicies.PostAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewClaimsMappingPolicy()
definition := []string {
	"{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}",
}
requestBody.SetDefinition(definition)
displayName := "AWS Claims Policy"
requestBody.SetDisplayName(&displayName)
isOrganizationDefault := false
requestBody.SetIsOrganizationDefault(&isOrganizationDefault)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
claimsMappingPolicies, err := graphClient.Policies().ClaimsMappingPolicies().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ClaimsMappingPolicy claimsMappingPolicy = new ClaimsMappingPolicy();
LinkedList<String> definition = new LinkedList<String>();
definition.add("{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}");
claimsMappingPolicy.setDefinition(definition);
claimsMappingPolicy.setDisplayName("AWS Claims Policy");
claimsMappingPolicy.setIsOrganizationDefault(false);
ClaimsMappingPolicy result = graphClient.policies().claimsMappingPolicies().post(claimsMappingPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const claimsMappingPolicy = {
    definition: [\
        '{\"ClaimsMappingPolicy\':{\'Version\':1,\'IncludeBasicClaimSet\':\'true\", \"ClaimsSchema\': [{\'Source\':\'user\",\"ID\':\'assignedroles\",\"SamlClaimType\': \'https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\':\'user\",\"ID\':\'userprincipalname\",\"SamlClaimType\': \'https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\':\'900\",\"SamlClaimType\': \'https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\':\'user\",\"ID\':\'assignedroles\",\"SamlClaimType\': \'appRoles\"}, {\"Source\':\'user\",\"ID\':\'userprincipalname\",\"SamlClaimType\': \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}"\
    ],
    displayName: 'AWS Claims Policy',
    isOrganizationDefault: false
};

await client.api('/policies/claimsMappingPolicies')
	.post(claimsMappingPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ClaimsMappingPolicy;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ClaimsMappingPolicy();
$requestBody->setDefinition(['{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}', 	]);
$requestBody->setDisplayName('AWS Claims Policy');
$requestBody->setIsOrganizationDefault(false);

$result = $graphServiceClient->policies()->claimsMappingPolicies()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.SignIns

$params = @{
	definition = @(
	'{"ClaimsMappingPolicy":{"Version":1,"IncludeBasicClaimSet":"true", "ClaimsSchema": [{"Source":"user","ID":"assignedroles","SamlClaimType": "https://aws.amazon.com/SAML/Attributes/Role"}, {"Source":"user","ID":"userprincipalname","SamlClaimType": "https://aws.amazon.com/SAML/Attributes/RoleSessionName"}, {"Value":"900","SamlClaimType": "https://aws.amazon.com/SAML/Attributes/SessionDuration"}, {"Source":"user","ID":"assignedroles","SamlClaimType": "appRoles"}, {"Source":"user","ID":"userprincipalname","SamlClaimType": "https://aws.amazon.com/SAML/Attributes/nameidentifier"}]}}'
)
displayName = "AWS Claims Policy"
isOrganizationDefault = $false
}

New-MgPolicyClaimMappingPolicy -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.claims_mapping_policy import ClaimsMappingPolicy
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ClaimsMappingPolicy(
	definition = [\
		"{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}",\
	],
	display_name = "AWS Claims Policy",
	is_organization_default = False,
)

result = await graph_client.policies.claims_mapping_policies.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#policies/claimsMappingPolicies/$entity",
    "id": "92037c7a-a875-49a0-814e-8ec30f880e2e",
    "deletedDateTime": null,
    "definition": [\
        "{\"ClaimsMappingPolicy\":{\"Version\":1,\"IncludeBasicClaimSet\":\"true\", \"ClaimsSchema\": [{\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/Role\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/RoleSessionName\"}, {\"Value\":\"900\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/SessionDuration\"}, {\"Source\":\"user\",\"ID\":\"assignedroles\",\"SamlClaimType\": \"appRoles\"}, {\"Source\":\"user\",\"ID\":\"userprincipalname\",\"SamlClaimType\": \"https://aws.amazon.com/SAML/Attributes/nameidentifier\"}]}}"\
    ],
    "displayName": "AWS Claims Policy",
    "isOrganizationDefault": false
}
```

### Step 5.2: Assign the claims mapping policy to the service principal

The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_7_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/servicePrincipals/ef04fead-8549-4e59-b5f7-d1d8c697ec64/claimsMappingPolicies/$ref
Content-type: application/json

{
    "@odata.id": "https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ReferenceCreate
{
	OdataId = "https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.ServicePrincipals["{servicePrincipal-id}"].ClaimsMappingPolicies.Ref.PostAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewReferenceCreate()
odataId := "https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e"
requestBody.SetOdataId(&odataId)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").ClaimsMappingPolicies().Ref().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.models.ReferenceCreate referenceCreate = new com.microsoft.graph.models.ReferenceCreate();
referenceCreate.setOdataId("https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e");
graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").claimsMappingPolicies().ref().post(referenceCreate);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const claimsMappingPolicy = {
    '@odata.id': 'https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e'
};

await client.api('/servicePrincipals/ef04fead-8549-4e59-b5f7-d1d8c697ec64/claimsMappingPolicies/$ref')
	.post(claimsMappingPolicy);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ReferenceCreate;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ReferenceCreate();
$requestBody->setOdataId('https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e');

$graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->claimsMappingPolicies()->ref()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	"@odata.id" = "https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e"
}

New-MgServicePrincipalClaimMappingPolicyByRef -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.reference_create import ReferenceCreate
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ReferenceCreate(
	odata_id = "https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/92037c7a-a875-49a0-814e-8ec30f880e2e",
)

await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').claims_mapping_policies.ref.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Step 6: Configure a signing certificate

You need a certificate that Microsoft Entra ID can use to sign a SAML response. You can use the `/addTokenSigningCertificate` endpoint to [create a token signing certificate for the service principal](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#option-1-create-a-token-signing-certificate-for-the-service-principal). Alternatively, you can [create a self-signed certificate and upload it to the service principal](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#option-2-create-a-custom-signing-certificate).

After you add the certificate, the service principal contains two objects in the **keyCredentials** collection: one for the private key and one for the public key; and an object in the **passwordCredentials** collection for the certificate password.

### Option 1: Create a token signing certificate for the service principal

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_8_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46/addTokenSigningCertificate
Content-type: application/json

{
    "displayName": "CN=AWSContoso",
    "endDateTime": "2027-01-22T00:00:00Z"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.ServicePrincipals.Item.AddTokenSigningCertificate;

var requestBody = new AddTokenSigningCertificatePostRequestBody
{
	DisplayName = "CN=AWSContoso",
	EndDateTime = DateTimeOffset.Parse("2027-01-22T00:00:00Z"),
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].AddTokenSigningCertificate.PostAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  "time"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphserviceprincipals "github.com/microsoftgraph/msgraph-sdk-go/serviceprincipals"
	  //other-imports
)

requestBody := graphserviceprincipals.NewAddTokenSigningCertificatePostRequestBody()
displayName := "CN=AWSContoso"
requestBody.SetDisplayName(&displayName)
endDateTime , err := time.Parse(time.RFC3339, "2027-01-22T00:00:00Z")
requestBody.SetEndDateTime(&endDateTime)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
addTokenSigningCertificate, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").AddTokenSigningCertificate().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

com.microsoft.graph.serviceprincipals.item.addtokensigningcertificate.AddTokenSigningCertificatePostRequestBody addTokenSigningCertificatePostRequestBody = new com.microsoft.graph.serviceprincipals.item.addtokensigningcertificate.AddTokenSigningCertificatePostRequestBody();
addTokenSigningCertificatePostRequestBody.setDisplayName("CN=AWSContoso");
OffsetDateTime endDateTime = OffsetDateTime.parse("2027-01-22T00:00:00Z");
addTokenSigningCertificatePostRequestBody.setEndDateTime(endDateTime);
SelfSignedCertificate result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").addTokenSigningCertificate().post(addTokenSigningCertificatePostRequestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const selfSignedCertificate = {
    displayName: 'CN=AWSContoso',
    endDateTime: '2027-01-22T00:00:00Z'
};

await client.api('/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46/addTokenSigningCertificate')
	.post(selfSignedCertificate);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\ServicePrincipals\Item\AddTokenSigningCertificate\AddTokenSigningCertificatePostRequestBody;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new AddTokenSigningCertificatePostRequestBody();
$requestBody->setDisplayName('CN=AWSContoso');
$requestBody->setEndDateTime(new \DateTime('2027-01-22T00:00:00Z'));

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->addTokenSigningCertificate()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	displayName = "CN=AWSContoso"
	endDateTime = [System.DateTime]::Parse("2027-01-22T00:00:00Z")
}

Add-MgServicePrincipalTokenSigningCertificate -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.serviceprincipals.item.add_token_signing_certificate.add_token_signing_certificate_post_request_body import AddTokenSigningCertificatePostRequestBody
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = AddTokenSigningCertificatePostRequestBody(
	display_name = "CN=AWSContoso",
	end_date_time = "2027-01-22T00:00:00Z",
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').add_token_signing_certificate.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#microsoft.graph.selfSignedCertificate",
    "customKeyIdentifier": "wt3YBEyVas0CaadaZLeGLbndrD4=",
    "displayName": "CN=AWSContoso",
    "endDateTime": "2027-01-22T00:00:00Z",
    "key": "MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=",
    "keyId": "04e5ac4e-31f9-41ad-83e2-6dd41e1d81f4",
    "startDateTime": "2024-02-21T17:09:35.0006942Z",
    "thumbprint": "C2DDD8044C956ACD0269A75A64B7862DB9DDAC3E",
    "type": "AsymmetricX509Cert",
    "usage": "Verify"
}
```

### Option 2: Create a custom signing certificate

You can use the following PowerShell and C# scripts to get a self-signed certificate for testing. Use your company's best security practices to create a signing certificate for production.

- [PowerShell script](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_9_powershell-script)
- [C# script](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_9_csharp-script)

The following script creates a self-signed certificate with the name you give in `fqdn` when prompted, for example, `CN=AWSContoso`. It protects the certificate with the password you supply in `pwd` and exports the PFX and CER certificates to the location you specify in `location`.

PowerShell

Copy

```powershell
Param(
    [Parameter(Mandatory=$true)]
    [string]$fqdn,
    [Parameter(Mandatory=$true)]
    [string]$pwd,
    [Parameter(Mandatory=$true)]
    [string]$location
)

if (!$PSBoundParameters.ContainsKey('location'))
{
    $location = "."
}

$cert = New-SelfSignedCertificate -certstorelocation cert:\currentuser\my -DnsName $fqdn
$pwdSecure = ConvertTo-SecureString -String $pwd -Force -AsPlainText
$path = 'cert:\currentuser\my\' + $cert.Thumbprint
$cerFile = $location + "\\" + $fqdn + ".cer"
$pfxFile = $location + "\\" + $fqdn + ".pfx"

Export-PfxCertificate -cert $path -FilePath $pfxFile -Password $pwdSecure
Export-Certificate -cert $path -FilePath $cerFile
```

The following C# console app can be used as a proof of concept to understand how the required values can be obtained. This code is for learning and reference only and shouldn't be used as-is in production.

C#

Copy

```csharp
using System;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

/* CONSOLE APP - PROOF OF CONCEPT CODE ONLY!!
 * This code uses a self signed certificate and should not be used
 * in production. This code is for reference and learning ONLY.
 */
namespace Self_signed_cert
{
    class Program
    {
        static void Main(string[] args)
        {
            // Generate a guid to use as a password and then create the cert.
            string password = Guid.NewGuid().ToString();
            var selfsignedCert = buildSelfSignedServerCertificate(password);

            // Print values so we can copy paste into the JSON fields.
            // Print out the private key in base64 format.
            Console.WriteLine("Private Key: {0}{1}", Convert.ToBase64String(selfsignedCert.Export(X509ContentType.Pfx, password)), Environment.NewLine);

            // Print out the start date in ISO 8601 format.
            DateTime startDate = DateTime.Parse(selfsignedCert.GetEffectiveDateString()).ToUniversalTime();
            Console.WriteLine("For All startDateTime: " + startDate.ToString("o"));

            // Print out the end date in ISO 8601 format.
            DateTime endDate = DateTime.Parse(selfsignedCert.GetExpirationDateString()).ToUniversalTime();
            Console.WriteLine("For All endDateTime: " + endDate.ToString("o"));

            // Print the GUID used for keyId
            string signAndPasswordGuid = Guid.NewGuid().ToString();
            string verifyGuid = Guid.NewGuid().ToString();
            Console.WriteLine("GUID to use for keyId for keyCredentials->Usage == Sign and passwordCredentials: " + signAndPasswordGuid);
            Console.WriteLine("GUID to use for keyId for keyCredentials->Usage == Verify: " + verifyGuid);

            // Print out the password.
            Console.WriteLine("Password is: {0}", password);

            // Print out a displayName to use as an example.
            Console.WriteLine("displayName to use: CN=Example");
            Console.WriteLine();

            // Print out the public key.
            Console.WriteLine("Public Key: {0}{1}", Convert.ToBase64String(selfsignedCert.Export(X509ContentType.Cert)), Environment.NewLine);
            Console.WriteLine();

            // Generate the customKeyIdentifier using hash of thumbprint.
            Console.WriteLine("You can generate the customKeyIdentifier by getting the SHA256 hash of the certs thumprint.\nThe certs thumbprint is: {0}{1}", selfsignedCert.Thumbprint, Environment.NewLine);
            Console.WriteLine("The hash of the thumbprint that we will use for customeKeyIdentifier is:");
            string keyIdentifier = GetSha256FromThumbprint(selfsignedCert.Thumbprint);
            Console.WriteLine(keyIdentifier);
        }

        // Generate a self-signed certificate.
        private static X509Certificate2 buildSelfSignedServerCertificate(string password)
        {
            const string CertificateName = @"Microsoft Azure Federated SSO Certificate TEST";
            DateTime certificateStartDate = DateTime.UtcNow;
            DateTime certificateEndDate = certificateStartDate.AddYears(2).ToUniversalTime();

            X500DistinguishedName distinguishedName = new X500DistinguishedName($"CN={CertificateName}");

            using (RSA rsa = RSA.Create(2048))
            {
                var request = new CertificateRequest(distinguishedName, rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);

                request.CertificateExtensions.Add(
                    new X509KeyUsageExtension(X509KeyUsageFlags.DataEncipherment | X509KeyUsageFlags.KeyEncipherment | X509KeyUsageFlags.DigitalSignature, false));

                var certificate = request.CreateSelfSigned(new DateTimeOffset(certificateStartDate), new DateTimeOffset(certificateEndDate));
                certificate.FriendlyName = CertificateName;

                return new X509Certificate2(certificate.Export(X509ContentType.Pfx, password), password, X509KeyStorageFlags.Exportable);
            }
        }

        // Generate hash from thumbprint.
        public static string GetSha256FromThumbprint(string thumbprint)
        {
            var message = Encoding.ASCII.GetBytes(thumbprint);
            SHA256Managed hashString = new SHA256Managed();
            return Convert.ToBase64String(hashString.ComputeHash(message));
        }
    }
}
```

#### Extract certificate details

From the previous step, you have the CER and PFX certificates. Extract the values for the private key, password, public key, and the certificate thumbprint to add to the service principal.

##### Extract the certificate thumbprint

###### Request

The following PowerShell script allows you to extract the thumbprint from the CER file. Replace the file path with the location of your certificate.

PowerShell

CopyOpen Cloud Shell

```powershell
## Replace the file path with the source of your certificate

Get-PfxCertificate -Filepath "C:\Users\admin\Desktop\CN=AWSContoso.cer" | Out-File -FilePath "C:\Users\admin\Desktop\CN=AWSContoso.cer.thumbprint.txt"
```

###### Response

The CN=AWSContoso.cer.thumbprint.txt file has an entry similar to the following output.

PowerShell

Copy

```powershell
Thumbprint                                Subject              EnhancedKeyUsageList
----------                                -------              --------------------
5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A  CN=AWSContoso        {Client Authentication, Server Authentication}
```

##### Extract the certificate key

The following PowerShell script allows you to extract the public key from the CER file. Replace the file path with the location of your certificate.

###### Request

PowerShell

CopyOpen Cloud Shell

```powershell
[convert]::ToBase64String((Get-Content C:\Users\admin\Desktop\CN=AWSContoso.cer -AsByteStream -Raw))  | Out-File -FilePath "C:\Users\admin\Desktop\CN=AWSContoso.cer.key.txt"
```

###### Response

The CN=AWSContoso.cer.key.txt file has an base64 encoded value similar to the following truncated output.

Bash

Copy

```bash
MIIDHjCCAgagAwIBAgIQYDbahiL7NY...6qCMVJKHAQGzGwg==
```

#### Add the custom signing key

Add the following details to the **keyCredentials** and **passwordCredentials** for the service principal. Where the two objects have the same properties, you must assign the same values for those properties.

- The **customKeyIdentifier** is the certificate thumbprint hash.
- The **startDateTime** is the date when or after the certificate was created.
- The **endDateTime** can be a maximum of three years from the **startDateTime**. If unspecified, the system automatically assigns a date one year after the startDateTime.
- The **type** and **usage** must be:

  - `AsymmetricX509Cert` and `Verify` respectively in the same object.
  - `X509CertAndPassword` and `Sign` respectively in the same object.
- Assign the certificate subject name to the **displayName** property.
- The **key** is the Base64 encoded value that you generated in the previous step.
- The **keyId** is a GUID that you can define.

The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_10_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/servicePrincipals/ef04fead-8549-4e59-b5f7-d1d8c697ec64
Content-type: application/json

{
    "keyCredentials": [\
        {\
            "customKeyIdentifier": "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A",\
            "endDateTime": "2027-01-22T00:00:00Z",\
            "keyId": "4c266507-3e74-4b91-aeba-18a25b450f6e",\
            "startDateTime": "2024-02-21T17:09:35Z",\
            "type": "X509CertAndPassword",\
            "usage": "Sign",\
            "key": "MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=",\
            "displayName": "CN=AWSContoso"\
        },\
        {\
            "customKeyIdentifier": "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A",\
            "endDateTime": "2027-01-22T00:00:00Z",\
            "keyId": "e35a7d11-fef0-49ad-9f3e-aacbe0a42c42",\
            "startDateTime": "2024-02-21T17:09:35Z",\
            "type": "AsymmetricX509Cert",\
            "usage": "Verify",\
            "key": "MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=",\
            "displayName": "CN=AWSContoso"\
        }\
    ],
    "passwordCredentials": [\
        {\
            "customKeyIdentifier": "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A",\
            "keyId": "4c266507-3e74-4b91-aeba-18a25b450f6e",\
            "endDateTime": "2022-01-27T19:40:33Z",\
            "startDateTime": "2027-01-22T00:00:00Z",\
            "secretText": "61891f4ee44d"\
        }\
    ]
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ServicePrincipal
{
	KeyCredentials = new List<KeyCredential>
	{
		new KeyCredential
		{
			CustomKeyIdentifier = Convert.FromBase64String("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"),
			EndDateTime = DateTimeOffset.Parse("2027-01-22T00:00:00Z"),
			KeyId = Guid.Parse("4c266507-3e74-4b91-aeba-18a25b450f6e"),
			StartDateTime = DateTimeOffset.Parse("2024-02-21T17:09:35Z"),
			Type = "X509CertAndPassword",
			Usage = "Sign",
			Key = Convert.FromBase64String("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs="),
			DisplayName = "CN=AWSContoso",
		},
		new KeyCredential
		{
			CustomKeyIdentifier = Convert.FromBase64String("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"),
			EndDateTime = DateTimeOffset.Parse("2027-01-22T00:00:00Z"),
			KeyId = Guid.Parse("e35a7d11-fef0-49ad-9f3e-aacbe0a42c42"),
			StartDateTime = DateTimeOffset.Parse("2024-02-21T17:09:35Z"),
			Type = "AsymmetricX509Cert",
			Usage = "Verify",
			Key = Convert.FromBase64String("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs="),
			DisplayName = "CN=AWSContoso",
		},
	},
	PasswordCredentials = new List<PasswordCredential>
	{
		new PasswordCredential
		{
			CustomKeyIdentifier = Convert.FromBase64String("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"),
			KeyId = Guid.Parse("4c266507-3e74-4b91-aeba-18a25b450f6e"),
			EndDateTime = DateTimeOffset.Parse("2022-01-27T19:40:33Z"),
			StartDateTime = DateTimeOffset.Parse("2027-01-22T00:00:00Z"),
			SecretText = "61891f4ee44d",
		},
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].PatchAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewServicePrincipal()

keyCredential := graphmodels.NewKeyCredential()
customKeyIdentifier := []byte("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A")
keyCredential.SetCustomKeyIdentifier(&customKeyIdentifier)
endDateTime , err := time.Parse(time.RFC3339, "2027-01-22T00:00:00Z")
keyCredential.SetEndDateTime(&endDateTime)
keyId := uuid.MustParse("4c266507-3e74-4b91-aeba-18a25b450f6e")
keyCredential.SetKeyId(&keyId)
startDateTime , err := time.Parse(time.RFC3339, "2024-02-21T17:09:35Z")
keyCredential.SetStartDateTime(&startDateTime)
type := "X509CertAndPassword"
keyCredential.SetType(&type)
usage := "Sign"
keyCredential.SetUsage(&usage)
key := []byte("mIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=")
keyCredential.SetKey(&key)
displayName := "CN=AWSContoso"
keyCredential.SetDisplayName(&displayName)
keyCredential1 := graphmodels.NewKeyCredential()
customKeyIdentifier := []byte("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A")
keyCredential1.SetCustomKeyIdentifier(&customKeyIdentifier)
endDateTime , err := time.Parse(time.RFC3339, "2027-01-22T00:00:00Z")
keyCredential1.SetEndDateTime(&endDateTime)
keyId := uuid.MustParse("e35a7d11-fef0-49ad-9f3e-aacbe0a42c42")
keyCredential1.SetKeyId(&keyId)
startDateTime , err := time.Parse(time.RFC3339, "2024-02-21T17:09:35Z")
keyCredential1.SetStartDateTime(&startDateTime)
type := "AsymmetricX509Cert"
keyCredential1.SetType(&type)
usage := "Verify"
keyCredential1.SetUsage(&usage)
key := []byte("mIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=")
keyCredential1.SetKey(&key)
displayName := "CN=AWSContoso"
keyCredential1.SetDisplayName(&displayName)

keyCredentials := []graphmodels.KeyCredentialable {
	keyCredential,
	keyCredential1,
}
requestBody.SetKeyCredentials(keyCredentials)

passwordCredential := graphmodels.NewPasswordCredential()
customKeyIdentifier := []byte("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A")
passwordCredential.SetCustomKeyIdentifier(&customKeyIdentifier)
keyId := uuid.MustParse("4c266507-3e74-4b91-aeba-18a25b450f6e")
passwordCredential.SetKeyId(&keyId)
endDateTime , err := time.Parse(time.RFC3339, "2022-01-27T19:40:33Z")
passwordCredential.SetEndDateTime(&endDateTime)
startDateTime , err := time.Parse(time.RFC3339, "2027-01-22T00:00:00Z")
passwordCredential.SetStartDateTime(&startDateTime)
secretText := "61891f4ee44d"
passwordCredential.SetSecretText(&secretText)

passwordCredentials := []graphmodels.PasswordCredentialable {
	passwordCredential,
}
requestBody.SetPasswordCredentials(passwordCredentials)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
servicePrincipals, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ServicePrincipal servicePrincipal = new ServicePrincipal();
LinkedList<KeyCredential> keyCredentials = new LinkedList<KeyCredential>();
KeyCredential keyCredential = new KeyCredential();
byte[] customKeyIdentifier = Base64.getDecoder().decode("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A");
keyCredential.setCustomKeyIdentifier(customKeyIdentifier);
OffsetDateTime endDateTime = OffsetDateTime.parse("2027-01-22T00:00:00Z");
keyCredential.setEndDateTime(endDateTime);
keyCredential.setKeyId(UUID.fromString("4c266507-3e74-4b91-aeba-18a25b450f6e"));
OffsetDateTime startDateTime = OffsetDateTime.parse("2024-02-21T17:09:35Z");
keyCredential.setStartDateTime(startDateTime);
keyCredential.setType("X509CertAndPassword");
keyCredential.setUsage("Sign");
byte[] key = Base64.getDecoder().decode("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=");
keyCredential.setKey(key);
keyCredential.setDisplayName("CN=AWSContoso");
keyCredentials.add(keyCredential);
KeyCredential keyCredential1 = new KeyCredential();
byte[] customKeyIdentifier1 = Base64.getDecoder().decode("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A");
keyCredential1.setCustomKeyIdentifier(customKeyIdentifier1);
OffsetDateTime endDateTime1 = OffsetDateTime.parse("2027-01-22T00:00:00Z");
keyCredential1.setEndDateTime(endDateTime1);
keyCredential1.setKeyId(UUID.fromString("e35a7d11-fef0-49ad-9f3e-aacbe0a42c42"));
OffsetDateTime startDateTime1 = OffsetDateTime.parse("2024-02-21T17:09:35Z");
keyCredential1.setStartDateTime(startDateTime1);
keyCredential1.setType("AsymmetricX509Cert");
keyCredential1.setUsage("Verify");
byte[] key1 = Base64.getDecoder().decode("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=");
keyCredential1.setKey(key1);
keyCredential1.setDisplayName("CN=AWSContoso");
keyCredentials.add(keyCredential1);
servicePrincipal.setKeyCredentials(keyCredentials);
LinkedList<PasswordCredential> passwordCredentials = new LinkedList<PasswordCredential>();
PasswordCredential passwordCredential = new PasswordCredential();
byte[] customKeyIdentifier2 = Base64.getDecoder().decode("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A");
passwordCredential.setCustomKeyIdentifier(customKeyIdentifier2);
passwordCredential.setKeyId(UUID.fromString("4c266507-3e74-4b91-aeba-18a25b450f6e"));
OffsetDateTime endDateTime2 = OffsetDateTime.parse("2022-01-27T19:40:33Z");
passwordCredential.setEndDateTime(endDateTime2);
OffsetDateTime startDateTime2 = OffsetDateTime.parse("2027-01-22T00:00:00Z");
passwordCredential.setStartDateTime(startDateTime2);
passwordCredential.setSecretText("61891f4ee44d");
passwordCredentials.add(passwordCredential);
servicePrincipal.setPasswordCredentials(passwordCredentials);
ServicePrincipal result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").patch(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const servicePrincipal = {
    keyCredentials: [\
        {\
            customKeyIdentifier: '5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A',\
            endDateTime: '2027-01-22T00:00:00Z',\
            keyId: '4c266507-3e74-4b91-aeba-18a25b450f6e',\
            startDateTime: '2024-02-21T17:09:35Z',\
            type: 'X509CertAndPassword',\
            usage: 'Sign',\
            key: 'MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=',\
            displayName: 'CN=AWSContoso'\
        },\
        {\
            customKeyIdentifier: '5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A',\
            endDateTime: '2027-01-22T00:00:00Z',\
            keyId: 'e35a7d11-fef0-49ad-9f3e-aacbe0a42c42',\
            startDateTime: '2024-02-21T17:09:35Z',\
            type: 'AsymmetricX509Cert',\
            usage: 'Verify',\
            key: 'MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=',\
            displayName: 'CN=AWSContoso'\
        }\
    ],
    passwordCredentials: [\
        {\
            customKeyIdentifier: '5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A',\
            keyId: '4c266507-3e74-4b91-aeba-18a25b450f6e',\
            endDateTime: '2022-01-27T19:40:33Z',\
            startDateTime: '2027-01-22T00:00:00Z',\
            secretText: '61891f4ee44d'\
        }\
    ]
};

await client.api('/servicePrincipals/ef04fead-8549-4e59-b5f7-d1d8c697ec64')
	.update(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ServicePrincipal;
use Microsoft\Graph\Generated\Models\KeyCredential;
use Microsoft\Graph\Generated\Models\PasswordCredential;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ServicePrincipal();
$keyCredentialsKeyCredential1 = new KeyCredential();
$keyCredentialsKeyCredential1->setCustomKeyIdentifier(\GuzzleHttp\Psr7\Utils::streamFor(base64_decode('5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A')));
$keyCredentialsKeyCredential1->setEndDateTime(new \DateTime('2027-01-22T00:00:00Z'));
$keyCredentialsKeyCredential1->setKeyId('4c266507-3e74-4b91-aeba-18a25b450f6e');
$keyCredentialsKeyCredential1->setStartDateTime(new \DateTime('2024-02-21T17:09:35Z'));
$keyCredentialsKeyCredential1->setType('X509CertAndPassword');
$keyCredentialsKeyCredential1->setUsage('Sign');
$keyCredentialsKeyCredential1->setKey(\GuzzleHttp\Psr7\Utils::streamFor(base64_decode('MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=')));
$keyCredentialsKeyCredential1->setDisplayName('CN=AWSContoso');
$keyCredentialsArray []= $keyCredentialsKeyCredential1;
$keyCredentialsKeyCredential2 = new KeyCredential();
$keyCredentialsKeyCredential2->setCustomKeyIdentifier(\GuzzleHttp\Psr7\Utils::streamFor(base64_decode('5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A')));
$keyCredentialsKeyCredential2->setEndDateTime(new \DateTime('2027-01-22T00:00:00Z'));
$keyCredentialsKeyCredential2->setKeyId('e35a7d11-fef0-49ad-9f3e-aacbe0a42c42');
$keyCredentialsKeyCredential2->setStartDateTime(new \DateTime('2024-02-21T17:09:35Z'));
$keyCredentialsKeyCredential2->setType('AsymmetricX509Cert');
$keyCredentialsKeyCredential2->setUsage('Verify');
$keyCredentialsKeyCredential2->setKey(\GuzzleHttp\Psr7\Utils::streamFor(base64_decode('MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=')));
$keyCredentialsKeyCredential2->setDisplayName('CN=AWSContoso');
$keyCredentialsArray []= $keyCredentialsKeyCredential2;
$requestBody->setKeyCredentials($keyCredentialsArray);

$passwordCredentialsPasswordCredential1 = new PasswordCredential();
$passwordCredentialsPasswordCredential1->setCustomKeyIdentifier(\GuzzleHttp\Psr7\Utils::streamFor(base64_decode('5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A')));
$passwordCredentialsPasswordCredential1->setKeyId('4c266507-3e74-4b91-aeba-18a25b450f6e');
$passwordCredentialsPasswordCredential1->setEndDateTime(new \DateTime('2022-01-27T19:40:33Z'));
$passwordCredentialsPasswordCredential1->setStartDateTime(new \DateTime('2027-01-22T00:00:00Z'));
$passwordCredentialsPasswordCredential1->setSecretText('61891f4ee44d');
$passwordCredentialsArray []= $passwordCredentialsPasswordCredential1;
$requestBody->setPasswordCredentials($passwordCredentialsArray);

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	keyCredentials = @(
		@{
			customKeyIdentifier = [System.Text.Encoding]::ASCII.GetBytes("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A")
			endDateTime = [System.DateTime]::Parse("2027-01-22T00:00:00Z")
			keyId = "4c266507-3e74-4b91-aeba-18a25b450f6e"
			startDateTime = [System.DateTime]::Parse("2024-02-21T17:09:35Z")
			type = "X509CertAndPassword"
			usage = "Sign"
			key = [System.Text.Encoding]::ASCII.GetBytes("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=")
			displayName = "CN=AWSContoso"
		}
		@{
			customKeyIdentifier = [System.Text.Encoding]::ASCII.GetBytes("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A")
			endDateTime = [System.DateTime]::Parse("2027-01-22T00:00:00Z")
			keyId = "e35a7d11-fef0-49ad-9f3e-aacbe0a42c42"
			startDateTime = [System.DateTime]::Parse("2024-02-21T17:09:35Z")
			type = "AsymmetricX509Cert"
			usage = "Verify"
			key = [System.Text.Encoding]::ASCII.GetBytes("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs=")
			displayName = "CN=AWSContoso"
		}
	)
	passwordCredentials = @(
		@{
			customKeyIdentifier = [System.Text.Encoding]::ASCII.GetBytes("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A")
			keyId = "4c266507-3e74-4b91-aeba-18a25b450f6e"
			endDateTime = [System.DateTime]::Parse("2022-01-27T19:40:33Z")
			startDateTime = [System.DateTime]::Parse("2027-01-22T00:00:00Z")
			secretText = "61891f4ee44d"
		}
	)
}

Update-MgServicePrincipal -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.service_principal import ServicePrincipal
from msgraph.generated.models.key_credential import KeyCredential
from msgraph.generated.models.password_credential import PasswordCredential
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ServicePrincipal(
	key_credentials = [\
		KeyCredential(\
			custom_key_identifier = base64.urlsafe_b64decode("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"),\
			end_date_time = "2027-01-22T00:00:00Z",\
			key_id = UUID("4c266507-3e74-4b91-aeba-18a25b450f6e"),\
			start_date_time = "2024-02-21T17:09:35Z",\
			type = "X509CertAndPassword",\
			usage = "Sign",\
			key = base64.urlsafe_b64decode("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs="),\
			display_name = "CN=AWSContoso",\
		),\
		KeyCredential(\
			custom_key_identifier = base64.urlsafe_b64decode("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"),\
			end_date_time = "2027-01-22T00:00:00Z",\
			key_id = UUID("e35a7d11-fef0-49ad-9f3e-aacbe0a42c42"),\
			start_date_time = "2024-02-21T17:09:35Z",\
			type = "AsymmetricX509Cert",\
			usage = "Verify",\
			key = base64.urlsafe_b64decode("MIICqjCCAZKgAwIBAgIIZYCy..KlDixjUT61i4tFs="),\
			display_name = "CN=AWSContoso",\
		),\
	],
	password_credentials = [\
		PasswordCredential(\
			custom_key_identifier = base64.urlsafe_b64decode("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"),\
			key_id = UUID("4c266507-3e74-4b91-aeba-18a25b450f6e"),\
			end_date_time = "2022-01-27T19:40:33Z",\
			start_date_time = "2027-01-22T00:00:00Z",\
			secret_text = "61891f4ee44d",\
		),\
	],
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Activate the custom signing key

You need to set the **preferredTokenSigningKeyThumbprint** property of the service principal to the thumbprint of the certificate that you want Microsoft Entra ID to use to sign the SAML response. The request returns a `204 No Content` response code.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_11_python)

HTTP

Copy

```http
PATCH https://graph.microsoft.com/v1.0/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46
Content-type: application/json

{
    "preferredTokenSigningKeyThumbprint": "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new ServicePrincipal
{
	PreferredTokenSigningKeyThumbprint = "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A",
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].PatchAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewServicePrincipal()
preferredTokenSigningKeyThumbprint := "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"
requestBody.SetPreferredTokenSigningKeyThumbprint(&preferredTokenSigningKeyThumbprint)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
servicePrincipals, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").Patch(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

ServicePrincipal servicePrincipal = new ServicePrincipal();
servicePrincipal.setPreferredTokenSigningKeyThumbprint("5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A");
ServicePrincipal result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").patch(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const servicePrincipal = {
    preferredTokenSigningKeyThumbprint: '5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A'
};

await client.api('/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46')
	.update(servicePrincipal);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\ServicePrincipal;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new ServicePrincipal();
$requestBody->setPreferredTokenSigningKeyThumbprint('5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A');

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->patch($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	preferredTokenSigningKeyThumbprint = "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A"
}

Update-MgServicePrincipal -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.service_principal import ServicePrincipal
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = ServicePrincipal(
	preferred_token_signing_key_thumbprint = "5214D6BA9438F984A0CC2C856CCEA6A76EDCEC3A",
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').patch(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Step 7: Assign users to the application

### Assign a user to the application

Assign the test user that you created to the service principal and grant them the `Admin,WAAD` app role. In the request body, provide the following values:

- **principalId** \- The ID of the user account that you created.
- **appRoleId** \- The ID of the `Admin,WAAD` app role that you added.
- **resourceId** \- The ID of the service principal.

#### Request

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_12_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46/appRoleAssignments
Content-type: application/json

{
    "principalId": "59bb3898-0621-4414-ac61-74f9d7201355",
    "principalType": "User",
    "appRoleId": "3a84e31e-bffa-470f-b9e6-754a61e4dc63",
    "resourceId": "d3616293-fff8-4415-9f01-33b05dad1b46"
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new AppRoleAssignment
{
	PrincipalId = Guid.Parse("59bb3898-0621-4414-ac61-74f9d7201355"),
	PrincipalType = "User",
	AppRoleId = Guid.Parse("3a84e31e-bffa-470f-b9e6-754a61e4dc63"),
	ResourceId = Guid.Parse("d3616293-fff8-4415-9f01-33b05dad1b46"),
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.ServicePrincipals["{servicePrincipal-id}"].AppRoleAssignments.PostAsync(requestBody);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Go

Copy

```go

// Code snippets are only available for the latest major version. Current major version is $v1.*

// Dependencies
import (
	  "context"
	  "github.com/google/uuid"
	  msgraphsdk "github.com/microsoftgraph/msgraph-sdk-go"
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewAppRoleAssignment()
principalId := uuid.MustParse("59bb3898-0621-4414-ac61-74f9d7201355")
requestBody.SetPrincipalId(&principalId)
principalType := "User"
requestBody.SetPrincipalType(&principalType)
appRoleId := uuid.MustParse("3a84e31e-bffa-470f-b9e6-754a61e4dc63")
requestBody.SetAppRoleId(&appRoleId)
resourceId := uuid.MustParse("d3616293-fff8-4415-9f01-33b05dad1b46")
requestBody.SetResourceId(&resourceId)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
appRoleAssignments, err := graphClient.ServicePrincipals().ByServicePrincipalId("servicePrincipal-id").AppRoleAssignments().Post(context.Background(), requestBody, nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

AppRoleAssignment appRoleAssignment = new AppRoleAssignment();
appRoleAssignment.setPrincipalId(UUID.fromString("59bb3898-0621-4414-ac61-74f9d7201355"));
appRoleAssignment.setPrincipalType("User");
appRoleAssignment.setAppRoleId(UUID.fromString("3a84e31e-bffa-470f-b9e6-754a61e4dc63"));
appRoleAssignment.setResourceId(UUID.fromString("d3616293-fff8-4415-9f01-33b05dad1b46"));
AppRoleAssignment result = graphClient.servicePrincipals().byServicePrincipalId("{servicePrincipal-id}").appRoleAssignments().post(appRoleAssignment);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const appRoleAssignment = {
    principalId: '59bb3898-0621-4414-ac61-74f9d7201355',
    principalType: 'User',
    appRoleId: '3a84e31e-bffa-470f-b9e6-754a61e4dc63',
    resourceId: 'd3616293-fff8-4415-9f01-33b05dad1b46'
};

await client.api('/servicePrincipals/d3616293-fff8-4415-9f01-33b05dad1b46/appRoleAssignments')
	.post(appRoleAssignment);
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\AppRoleAssignment;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new AppRoleAssignment();
$requestBody->setPrincipalId('59bb3898-0621-4414-ac61-74f9d7201355');
$requestBody->setPrincipalType('User');
$requestBody->setAppRoleId('3a84e31e-bffa-470f-b9e6-754a61e4dc63');
$requestBody->setResourceId('d3616293-fff8-4415-9f01-33b05dad1b46');

$result = $graphServiceClient->servicePrincipals()->byServicePrincipalId('servicePrincipal-id')->appRoleAssignments()->post($requestBody)->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

$params = @{
	principalId = "59bb3898-0621-4414-ac61-74f9d7201355"
	principalType = "User"
	appRoleId = "3a84e31e-bffa-470f-b9e6-754a61e4dc63"
	resourceId = "d3616293-fff8-4415-9f01-33b05dad1b46"
}

New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $servicePrincipalId -BodyParameter $params
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.app_role_assignment import AppRoleAssignment
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = AppRoleAssignment(
	principal_id = UUID("59bb3898-0621-4414-ac61-74f9d7201355"),
	principal_type = "User",
	app_role_id = UUID("3a84e31e-bffa-470f-b9e6-754a61e4dc63"),
	resource_id = UUID("d3616293-fff8-4415-9f01-33b05dad1b46"),
)

result = await graph_client.service_principals.by_service_principal_id('servicePrincipal-id').app_role_assignments.post(request_body)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

#### Response

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#servicePrincipals('d3616293-fff8-4415-9f01-33b05dad1b46')/appRoleAssignments/$entity",
    "id": "mDi7WSEGFESsYXT51yATVdouI-92Rw1OgPSpSxEvaLg",
    "deletedDateTime": null,
    "appRoleId": "3a84e31e-bffa-470f-b9e6-754a61e4dc63",
    "createdDateTime": "2024-02-21T18:07:54.7959075Z",
    "principalDisplayName": "Adele Vance",
    "principalId": "59bb3898-0621-4414-ac61-74f9d7201355",
    "principalType": "User",
    "resourceDisplayName": "AWS Contoso",
    "resourceId": "d3616293-fff8-4415-9f01-33b05dad1b46"
}
```

## Step 8: Get Microsoft Entra ID SAML metadata for AWS Contoso app

Use the following URL to get the Microsoft Entra ID SAML metadata for AWS Contoso app. Replace `{tenant-id}` with the tenant ID and `{appId}` with the appId of the AWS Contoso app. The metadata contains information such as the signing certificate, Microsoft Entra entityID, and Microsoft Entra SingleSignOnService, among others.

`https://login.microsoftonline.com/{tenant-id}/federationmetadata/2007-06/federationmetadata.xml?appid={appId}`

The following shows an example of what you see for your application. Save the data in XML format.

XML

Copy

```xml
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" ID="_26313693-22d4-4361-8e48-ea19bb8616e1" entityID="https://sts.windows.net/38d49456-54d4-455d-a8d6-c383c71e0a6d/">
<RoleDescriptor xmlns:fed="http://docs.oasis-open.org/wsfed/federation/200706" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="fed:SecurityTokenServiceType" protocolSupportEnumeration="http://docs.oasis-open.org/wsfed/federation/200706">
<fed:ClaimTypesOffered>
...
<IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
<SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://login.microsoftonline.com/38d49456-54d4-455d-a8d6-c383c71e0a6d/saml2"/>
<SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://login.microsoftonline.com/38d49456-54d4-455d-a8d6-c383c71e0a6d/saml2"/>
<SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Location="https://login.microsoftonline.com/38d49456-54d4-455d-a8d6-c383c71e0a6d/saml2"/>
</IDPSSODescriptor>
</EntityDescriptor>
```

## Step 9: Complete and test the integration

Now that you've configured the Microsoft Entra application and have the SAML metadata, sign in to your AWS IAM Identity Center company site as an administrator and:

1. [Configure AWS IAM Identity Center SSO](https://learn.microsoft.com/en-us/entra/identity/saas-apps/aws-single-sign-on-tutorial#configure-aws-iam-identity-center-sso).
2. [Create an AWS IAM Identity Center test user whose user name and email address match the user account that you created in Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity/saas-apps/aws-single-sign-on-tutorial#create-aws-iam-identity-center-test-user).
3. [Test the SSO integration](https://learn.microsoft.com/en-us/entra/identity/saas-apps/aws-single-sign-on-tutorial#test-sso).

[Section titled: [Optional] Step 10: Clean up resources](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#optional-step-10-clean-up-resources)

## \[Optional\] Step 10: Clean up resources

In this step, remove the resources that you created and no longer need.

### Delete the application

When you delete the application, the service principal in your tenant is also deleted. The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_13_python)

HTTP

Copy

```http
DELETE https://graph.microsoft.com/v1.0/applications/b7308000-8bb3-467b-bfc7-8dbbfd759ad9
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.Applications["{application-id}"].DeleteAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

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
graphClient.Applications().ByApplicationId("application-id").Delete(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

graphClient.applications().byApplicationId("{application-id}").delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

await client.api('/applications/b7308000-8bb3-467b-bfc7-8dbbfd759ad9')
	.delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$graphServiceClient->applications()->byApplicationId('application-id')->delete()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Applications

Remove-MgApplication -ApplicationId $applicationId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

await graph_client.applications.by_application_id('application-id').delete()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Delete the test user account

The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_14_python)

HTTP

Copy

```http
DELETE https://graph.microsoft.com/v1.0/users/59bb3898-0621-4414-ac61-74f9d7201355
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.Users["{user-id}"].DeleteAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

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
graphClient.Users().ByUserId("user-id").Delete(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

graphClient.users().byUserId("{user-id}").delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

await client.api('/users/59bb3898-0621-4414-ac61-74f9d7201355')
	.delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$graphServiceClient->users()->byUserId('user-id')->delete()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Users

Remove-MgUser -UserId $userId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

await graph_client.users.by_user_id('user-id').delete()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

### Delete the claims mapping policy

The request returns a `204 No Content` response code.

- [HTTP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_http)
- [C#](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_go)
- [Java](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/application-saml-sso-configure-api?tabs=http%2Cpowershell-script#tabpanel_15_python)

HTTP

Copy

```http
DELETE https://graph.microsoft.com/v1.0/policies/claimsMappingPolicies/a4b35718-fd5e-4ca8-8248-a3c9934b1b78
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
await graphClient.Policies.ClaimsMappingPolicies["{claimsMappingPolicy-id}"].DeleteAsync();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

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
graphClient.Policies().ClaimsMappingPolicies().ByClaimsMappingPolicyId("claimsMappingPolicy-id").Delete(context.Background(), nil)
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

graphClient.policies().claimsMappingPolicies().byClaimsMappingPolicyId("{claimsMappingPolicy-id}").delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

await client.api('/policies/claimsMappingPolicies/a4b35718-fd5e-4ca8-8248-a3c9934b1b78')
	.delete();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$graphServiceClient->policies()->claimsMappingPolicies()->byClaimsMappingPolicyId('claimsMappingPolicy-id')->delete()->wait();
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.Identity.SignIns

Remove-MgPolicyClaimMappingPolicy -ClaimsMappingPolicyId $claimsMappingPolicyId
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python

await graph_client.policies.claims_mapping_policies.by_claims_mapping_policy_id('claimsMappingPolicy-id').delete()
```

> Read the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview) for details on how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance.

## Related content

- Review the [steps to integrate Microsoft Entra SSO with AWS IAM Identity Center using the Microsoft Entra admin center](https://learn.microsoft.com/en-us/entra/identity/saas-apps/aws-single-sign-on-tutorial).

* * *
