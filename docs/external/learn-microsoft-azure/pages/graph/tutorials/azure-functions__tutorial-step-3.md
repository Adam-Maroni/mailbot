# Microsoft Graph sample Azure Function

[Permalink: Microsoft Graph sample Azure Function](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#microsoft-graph-sample-azure-function)

[![.NET](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/actions/workflows/dotnet.yml/badge.svg)](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/actions/workflows/dotnet.yml)![License.](https://camo.githubusercontent.com/8bb50fd2278f18fc326bf71f6e88ca8f884f72f179d3e555e20ed30157190d0d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d677265656e2e737667)

This sample demonstrates how to use the Microsoft Graph .NET SDK to access data in Office 365 from Azure Functions.

> **NOTE:** This sample was originally built from a tutorial published on the [Microsoft Graph tutorials](https://learn.microsoft.com/graph/tutorials) page. That tutorial has been removed.

## Prerequisites

[Permalink: Prerequisites](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#prerequisites)

- [.NET SDK](https://dotnet.microsoft.com/download)
- [Azure Functions Core Tools](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- [ngrok](https://ngrok.com/)

## App registrations

[Permalink: App registrations](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#app-registrations)

This sample requires three Azure AD application registrations:

- An app registration for the single-page application so that it can sign in users and get tokens allowing the application to call the Azure Function.
- An app registration for the Azure Function that allows it to use the [on-behalf-of flow](https://learn.microsoft.com/azure/active-directory/develop/v2-oauth2-on-behalf-of-flow) to exchange the token sent by the SPA for a token that will allow it to call Microsoft Graph.
- An app registration for the Azure Function webhook that allows it to use the [client credential flow](https://learn.microsoft.com/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow) to call Microsoft Graph without a user.

> **NOTE**
> This example requires three app registrations because it is implementing both the on-behalf-of flow and the client credential flow. If your Azure Function only uses one of these flows, you would only need to create the app registrations that correspond to that flow.

1. Open a browser and navigate to the [Azure Active Directory admin center](https://aad.portal.azure.com/) and login using an Microsoft 365 tenant organization admin.

2. Select **Azure Active Directory** in the left-hand navigation, then select **App registrations** under **Manage**.

### Register an app for the single-page application

[Permalink: Register an app for the single-page application](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#register-an-app-for-the-single-page-application)

1. Select **New registration**. On the **Register an application** page, set the values as follows.
   - Set **Name** to `Graph Azure Function Test App`.
   - Set **Supported account types** to **Accounts in this organizational directory only**.
   - Under **Redirect URI**, change the dropdown to **Single-page application (SPA)** and set the value to `http://localhost:8080`.
2. Select **Register**. On the **Graph Azure Function Test App** page, copy the values of the **Application (client) ID** and **Directory (tenant) ID** and save them, you will need them in the later steps.

### Register an app for the Azure Function

[Permalink: Register an app for the Azure Function](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#register-an-app-for-the-azure-function)

01. Return to **App Registrations**, and select **New registration**. On the **Register an application** page, set the values as follows.
    - Set **Name** to `Graph Azure Function`.
    - Set **Supported account types** to **Accounts in this organizational directory only**.
    - Leave **Redirect URI** blank.
02. Select **Register**. On the **Graph Azure Function** page, copy the value of the **Application (client) ID** and save it, you will need it in the next step.

03. Select **Certificates & secrets** under **Manage**. Select the **New client secret** button. Enter a value in **Description** and select one of the options for **Expires** and select **Add**.

04. Copy the client secret value before you leave this page. You will need it in the next step.

    > **IMPORTANT**
    > This client secret is never shown again, so make sure you copy it now.

05. Select **API Permissions** under **Manage**. Choose **Add a permission**.

06. Select **Microsoft Graph**, then **Delegated Permissions**. Add **Mail.Read** and select **Add permissions**.

07. Select **Expose an API** under **Manage**, then choose **Add a scope**.

08. Accept the default **Application ID URI** and choose **Save and continue**.

09. Fill in the **Add a scope** form as follows:
    - **Scope name:** Mail.Read
    - **Who can consent?:** Admins and users
    - **Admin consent display name:** Read all users' inboxes
    - **Admin consent description:** Allows the app to read all users' inboxes
    - **User consent display name:** Read your inbox
    - **User consent description:** Allows the app to read your inbox
    - **State:** Enabled
10. Select **Add scope**.

11. Copy the new scope, you'll need it in later steps.

12. Select **Manifest** under **Manage**.

13. Locate `knownClientApplications` in the manifest, and replace it's current value of `[]` with `["TEST_APP_ID"]`, where `TEST_APP_ID` is the application ID of the **Graph Azure Function Test App** app registration. Select **Save**.

> **NOTE**
> Adding the test application's app ID to the `knownClientApplications` property in the Azure Function's manifest allows the test application to trigger a [combined consent flow](https://learn.microsoft.com/azure/active-directory/develop/v2-oauth2-on-behalf-of-flow#default-and-combined-consent). This is necessary for the on-behalf-of flow to work.

### Add Azure Function scope to test application registration

[Permalink: Add Azure Function scope to test application registration](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#add-azure-function-scope-to-test-application-registration)

1. Return to the **Graph Azure Function Test App** registration, and select **API Permissions** under **Manage**. Select **Add a permission**.

2. Select **My APIs**, then select **Load more**. Select **Graph Azure Function**.

3. Select the **Mail.Read** permission, then select **Add permissions**.

4. In the **Configured permissions**, remove the **User.Read** permission under **Microsoft Graph** by selecting the **...** to the right of the permission and selecting **Remove permission**. Select **Yes, remove** to confirm.

### Register an app for the Azure Function webhook

[Permalink: Register an app for the Azure Function webhook](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#register-an-app-for-the-azure-function-webhook)

1. Return to **App Registrations**, and select **New registration**. On the **Register an application** page, set the values as follows.
   - Set **Name** to `Graph Azure Function Webhook`.
   - Set **Supported account types** to **Accounts in this organizational directory only**.
   - Leave **Redirect URI** blank.
2. Select **Register**. On the **Graph Azure Function webhook** page, copy the value of the **Application (client) ID** and save it, you will need it in the next step.

3. Select **Certificates & secrets** under **Manage**. Select the **New client secret** button. Enter a value in **Description** and select one of the options for **Expires** and select **Add**.

4. Copy the client secret value before you leave this page. You will need it in the next step.

5. Select **API Permissions** under **Manage**. Choose **Add a permission**.

6. Select **Microsoft Graph**, then **Application Permissions**. Add **User.Read.All** and **Mail.Read**, then select **Add permissions**.

7. In the **Configured permissions**, remove the delegated **User.Read** permission under **Microsoft Graph** by selecting the **...** to the right of the permission and selecting **Remove permission**. Select **Yes, remove** to confirm.

8. Select the **Grant admin consent for...** button, then select **Yes** to grant admin consent for the configured application permissions. The **Status** column in the **Configured permissions** table changes to **Granted for ...**.

## Configure the sample

[Permalink: Configure the sample](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#configure-the-sample)

1. Run ngrok using the following command. (Only required if using the change notification webhook portion of the sample)

```
ngrok http 7071
```

2. Rename [config.example.js](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/blob/main/TestClient/config.example.js) to **config.js** and replace the following values:
   - `YOUR_TEST_APP_CLIENT_ID_HERE` \- replace with the client ID for **Graph Azure Function Test App**
   - `YOUR_TENANT_ID_HERE` \- replace with your tenant ID
   - `YOUR_AZURE_FUNCTION_CLIENT_ID_HERE` \- replace with the client ID for **Graph Azure Function**
3. Use `dotnet user-secrets set` in the **GraphSampleFunctions** directory to set the following values.
   - apiClientId - the client ID for **Graph Azure Function**
   - apiClientSecret - the client secret for **Graph Azure Function**
   - ngrokUrl - your ngrok URL (copy from ngrok output)
   - tenantId - your tenant ID
   - webhookClientId - the client ID for **Graph Azure Function Webhook**
   - webhookClientSecret - the client secret for **Graph Azure Function Webhook**

> **NOTE**
> If you restart ngrok, you will need to update the `ngrokUrl` value in user secrets with the new ngrok URL and restart the Azure Function project.

## Run the sample

[Permalink: Run the sample](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#run-the-sample)

The following command (run in the **GraphSampleFunctions** directory) will start the Azure Function project locally on your machine.

```
func start
```

To serve the test client, run your favorite command-line HTTP server in the **TestClient** directory. For example, you can use [dotnet-serve](https://github.com/natemcmaster/dotnet-serve).

```
dotnet serve -h "Cache-Control: no-cache, no-store, must-revalidate" -p 8080
```

Open your browser to `http://localhost:8080` and sign in with a user in your tenant.

## Code of conduct

[Permalink: Code of conduct](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#code-of-conduct)

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Disclaimer

[Permalink: Disclaimer](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#disclaimer)

**THIS CODE IS PROVIDED _AS IS_ WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING ANY IMPLIED WARRANTIES OF FITNESS FOR A PARTICULAR PURPOSE, MERCHANTABILITY, OR NON-INFRINGEMENT.**

## About

This sample demonstrates how to use the Microsoft Graph .NET SDK to access data in Office 365 from Azure Functions.

### Topics

[csharp](https://github.com/topics/csharp "Topic: csharp") [azure-functions](https://github.com/topics/azure-functions "Topic: azure-functions") [microsoft-graph](https://github.com/topics/microsoft-graph "Topic: microsoft-graph") [devxsample](https://github.com/topics/devxsample "Topic: devxsample")

### Resources

[Readme](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#readme-ov-file)

### License

[MIT license](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#MIT-1-ov-file)

### Code of conduct

[Code of conduct](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp#coc-ov-file)

### Uh oh!

There was an error while loading. [Please reload this page](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp).

[Activity](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/activity)

[Custom properties](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/custom-properties)

### Stars

[**50**\\
stars](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/stargazers)

### Watchers

[**5**\\
watching](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/watchers)

### Forks

[**23**\\
forks](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/forks)

[Report repository](https://github.com/contact/report-content?content_url=https%3A%2F%2Fgithub.com%2Fmicrosoftgraph%2Fmsgraph-sample-azurefunction-csharp&report=microsoftgraph+%28user%29)

## [Releases](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/releases)

No releases published

## [Packages\  0](https://github.com/orgs/microsoftgraph/packages?repo_name=msgraph-sample-azurefunction-csharp)

No packages published

### Uh oh!

There was an error while loading. [Please reload this page](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp).

## [Contributors\  8](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/graphs/contributors)

- [![@dependabot[bot]](https://avatars.githubusercontent.com/in/29110?s=64&v=4)](https://github.com/apps/dependabot)
- [![@github-actions[bot]](https://avatars.githubusercontent.com/in/15368?s=64&v=4)](https://github.com/apps/github-actions)
- [![@jasonjoh](https://avatars.githubusercontent.com/u/8966342?s=64&v=4)](https://github.com/jasonjoh)
- [![@philip-young](https://avatars.githubusercontent.com/u/62968356?s=64&v=4)](https://github.com/philip-young)
- [![@microsoft-github-policy-service[bot]](https://avatars.githubusercontent.com/in/95686?s=64&v=4)](https://github.com/apps/microsoft-github-policy-service)
- [![@baywet](https://avatars.githubusercontent.com/u/7905502?s=64&v=4)](https://github.com/baywet)
- [![@daxianji007](https://avatars.githubusercontent.com/u/8327019?s=64&v=4)](https://github.com/daxianji007)
- [![@mtrilbybassett](https://avatars.githubusercontent.com/u/49200399?s=64&v=4)](https://github.com/mtrilbybassett)

## Languages

- [C#55.2%](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/search?l=c%23)
- [JavaScript38.7%](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/search?l=javascript)
- [HTML6.0%](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/search?l=html)
- [CSS0.1%](https://github.com/microsoftgraph/msgraph-sample-azurefunction-csharp/search?l=css)

You can’t perform that action at this time.
