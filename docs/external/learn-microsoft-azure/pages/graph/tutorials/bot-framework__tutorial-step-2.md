# Microsoft Graph Bot Framework sample

[Permalink: Microsoft Graph Bot Framework sample](https://github.com/microsoftgraph/msgraph-sample-botframework#microsoft-graph-bot-framework-sample)

[![.NET](https://github.com/microsoftgraph/msgraph-training-botframework/actions/workflows/dotnet.yml/badge.svg)](https://github.com/microsoftgraph/msgraph-training-botframework/actions/workflows/dotnet.yml)![License.](https://camo.githubusercontent.com/8bb50fd2278f18fc326bf71f6e88ca8f884f72f179d3e555e20ed30157190d0d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d677265656e2e737667)

This sample demonstrates how to use the Microsoft Graph .NET SDK to access data in Office 365 from Microsoft Bot Framework bots.

> **NOTE:** This sample was originally built from a tutorial published on the [Microsoft Graph tutorials](https://docs.microsoft.com/graph/tutorials) page. That tutorial has been removed.

## Prerequisites

[Permalink: Prerequisites](https://github.com/microsoftgraph/msgraph-sample-botframework#prerequisites)

To run the completed project in this folder, you need the following:

- The [.NET Core SDK](https://dotnet.microsoft.com/download) 6.x installed on your development machine.
- [Bot Framework Emulator](https://github.com/microsoft/BotFramework-Emulator)
- [ngrok](https://ngrok.com/)
- Either a personal Microsoft account with a mailbox on Outlook.com, or a Microsoft work or school account with an Exchange Online mailbox.
- An Azure subscription and an account with the **Application developer**, **Application administrator**, **Cloud application administrator**, or **Global administrator** role.

If you don't have a Microsoft account, there are a couple of options to get a free account:

- You can [sign up for a new personal Microsoft account](https://signup.live.com/signup?wa=wsignin1.0&rpsnv=12&ct=1454618383&rver=6.4.6456.0&wp=MBI_SSL_SHARED&wreply=https://mail.live.com/default.aspx&id=64855&cbcxt=mai&bk=1454618383&uiflavor=web&uaid=b213a65b4fdc484382b6622b3ecaa547&mkt=E-US&lc=1033&lic=1).
- You can [sign up for the Microsoft 365 Developer Program](https://developer.microsoft.com/microsoft-365/dev-program) to get a free Office 365 subscription.

If you don't have an Azure subscription, you can [create an account for free](https://azure.microsoft.com/free/?WT.mc_id=A261C142F).

## Create an Azure Bot in Azure portal

[Permalink: Create an Azure Bot in Azure portal](https://github.com/microsoftgraph/msgraph-sample-botframework#create-an-azure-bot-in-azure-portal)

01. Open a browser and navigate to the [Azure Portal](https://portal.azure.com/). Login using the account associated with your Azure subscription.

02. Select the upper-left menu, then select **Create a resource**.

03. On the **New** page, search for `Azure Bot` and select **Azure Bot**.

04. On the **Azure Bot** page, select **Create**.

05. Fill in the required fields. The **Bot handle** field must be unique. Be sure to review the different pricing tiers and select what makes sense for your scenario. If this is just a learning exercise, you may want to select the free option.

06. For **Type of App**, select **Multi Tenant**.

07. For **Creation type**, select **Create new Microsoft App ID**.

08. Select **Review + create**. Once validation completes, select **Create**.

09. Once deployment has finished, select **Go to resource**.

10. Under **Settings**, select **Configuration**. Select the **Manage** link next to **Microsoft App ID**.

11. Select **New client secret**. Add a description and choose an expiration, then select **Add**.

12. Copy the client secret value before you leave this page. You will need it in the following steps.

    > \[!IMPORTANT\]
    > This client secret is never shown again, so make sure you copy it now. You will need to enter this value in multiple places so keep it safe.

13. Select **Overview** in the left-hand menu. Copy the value of the **Application (client) ID** and save it, you will need it in the following steps.

### Create a web app registration

[Permalink: Create a web app registration](https://github.com/microsoftgraph/msgraph-sample-botframework#create-a-web-app-registration)

1. Return to the home page of the Azure portal, then select **Azure Active Directory**.

2. Select **App registrations**.

3. Select **New registration**. On the **Register an application** page, set the values as follows.

   - Set **Name** to `Graph Calendar Bot Auth`.
   - Set **Supported account types** to **Accounts in any organizational directory and personal Microsoft accounts**.
   - Under **Redirect URI**, set the first drop-down to `Web` and set the value to `https://token.botframework.com/.auth/web/redirect`.

> **NOTE:**`https://token.botframework.com/.auth/web/redirect` is the default Bot Framework OAuth redirect URL for the public Azure cloud with no data residency requirements. Depending on your environment, you may need to use a different redirect URL. See [OAuth URL support in Azure Bot Service](https://docs.microsoft.com/azure/bot-service/ref-oauth-redirect-urls?view=azure-bot-service-4.0) for more information.

4. Select **Register**. On the **Graph Calendar Bot Auth** page, copy the value of the **Application (client) ID** and save it, you will need it in the following steps.

5. Select **Certificates & secrets** under **Manage**. Select the **New client secret** button. Enter a value in **Description** and select one of the options for **Expires** and select **Add**.

6. Copy the client secret value before you leave this page. You will need it in the following steps.

7. Select **API permissions**, then select **Add a permission**.

8. Select **Microsoft Graph**, then select **Delegated permissions**.

9. Select the following permissions, then select **Add permissions**.
   - **openid**
   - **profile**
   - **Calendars.ReadWrite**
   - **MailboxSettings.Read**

## Configure the sample

[Permalink: Configure the sample](https://github.com/microsoftgraph/msgraph-sample-botframework#configure-the-sample)

1. Create a new file in the **GraphCalendarBot** directory named **appsettings.Development.json** and add the following code.

```
{
     "MicrosoftAppId": "YOUR_BOT_APP_ID_HERE",
     "MicrosoftAppPassword": "YOUR_BOT_PASSWORD_HERE"
}
```

2. Replace `YOUR_BOT_APP_ID_HERE` with the **Application (client) ID** of your bot. (Step 13 of [Create an Azure Bot in Azure portal](https://github.com/microsoftgraph/msgraph-sample-botframework#create-an-azure-bot-in-azure-portal))

3. Replace `YOUR_BOT_PASSWORD_HERE` with the client secret of your bot. (Step 12 of [Create an Azure Bot in Azure portal](https://github.com/microsoftgraph/msgraph-sample-botframework#create-an-azure-bot-in-azure-portal))

## Running the sample

[Permalink: Running the sample](https://github.com/microsoftgraph/msgraph-sample-botframework#running-the-sample)

You can run this sample from your command-line interface (CLI), Visual Studio Code, or Visual Studio.

### CLI

[Permalink: CLI](https://github.com/microsoftgraph/msgraph-sample-botframework#cli)

1. In your CLI, navigate to the **GraphCalendarBot** directory.

2. Run the bot with the following command.

```
dotnet run
```

### Visual Studio Code

[Permalink: Visual Studio Code](https://github.com/microsoftgraph/msgraph-sample-botframework#visual-studio-code)

1. In Visual Studio Code, select **File**, then **Open Folder...**.
2. Browse to the folder where you cloned this repository and select **Select Folder**.
3. Select **Run**, then **Start Debugging**. (or press **F5**)

### Visual Studio

[Permalink: Visual Studio](https://github.com/microsoftgraph/msgraph-sample-botframework#visual-studio)

1. Open the **GraphCalendarBot.csproj** file in Visual Studio.
2. Press `F5` to run the project.

## Testing the bot using Bot Framework Emulator

[Permalink: Testing the bot using Bot Framework Emulator](https://github.com/microsoftgraph/msgraph-sample-botframework#testing-the-bot-using-bot-framework-emulator)

01. Open the Bot Framework Emulator. Select the gear icon ⚙ on the bottom left.

02. Enter the local path to your installation of ngrok, and enable the **Bypass ngrok for local addresses** and **Run ngrok when the Emulator starts up** options.

03. Enable the **Use a sign-in verification code for OAuthCards** option. Select **Save**.

04. Select the **File** menu, then **New Bot Configuration...**.

05. Fill in the fields as follows.
    - **Bot name:**`CalendarBot`
    - **Endpoint URL:**`http://localhost:3978/api/messages`
    - **Microsoft App ID:** the application ID of your **Graph Calendar Bot** app registration
    - **Microsoft App password:** your **Graph Calendar Bot** client secret
    - **Encrypt keys stored in your bot configuration:** Enabled
06. Select **Save and connect**. After the emulator connects, you should see `Welcome to Microsoft Graph CalendarBot. Type anything to get started.`

07. Type some text and send it to the bot. The bot responds with a login prompt.

08. Select the **Login** button. The emulator prompts you to confirm the URL that starts with `oauthlink://https://token.botframeworkcom`. Select **Confirm** to continue.

09. In the pop-up window, login with your Microsoft 365 account. Review the requested permissions and accept.

10. Once authentication and consent are complete, the pop-up window provides a validation code. Copy the code and close the window.

11. Enter the validation code in the chat window to complete the login.

12. Try the options presented by the bot after login.

[![A screenshot of the bot in Bot Framework Emulator](https://github.com/microsoftgraph/msgraph-sample-botframework/raw/main/emulator.png)](https://github.com/microsoftgraph/msgraph-sample-botframework/blob/main/emulator.png)

## Code of conduct

[Permalink: Code of conduct](https://github.com/microsoftgraph/msgraph-sample-botframework#code-of-conduct)

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Disclaimer

[Permalink: Disclaimer](https://github.com/microsoftgraph/msgraph-sample-botframework#disclaimer)

**THIS CODE IS PROVIDED _AS IS_ WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING ANY IMPLIED WARRANTIES OF FITNESS FOR A PARTICULAR PURPOSE, MERCHANTABILITY, OR NON-INFRINGEMENT.**

## About

This sample demonstrates how to use the Microsoft Graph .NET SDK to access data in Office 365 from Microsoft Bot Framework bots.

### Topics

[bot-framework](https://github.com/topics/bot-framework "Topic: bot-framework") [microsoft-graph](https://github.com/topics/microsoft-graph "Topic: microsoft-graph") [devxsample](https://github.com/topics/devxsample "Topic: devxsample")

### Resources

[Readme](https://github.com/microsoftgraph/msgraph-sample-botframework#readme-ov-file)

### License

[MIT license](https://github.com/microsoftgraph/msgraph-sample-botframework#MIT-1-ov-file)

### Code of conduct

[Code of conduct](https://github.com/microsoftgraph/msgraph-sample-botframework#coc-ov-file)

### Security policy

[Security policy](https://github.com/microsoftgraph/msgraph-sample-botframework#security-ov-file)

### Uh oh!

There was an error while loading. [Please reload this page](https://github.com/microsoftgraph/msgraph-sample-botframework).

[Activity](https://github.com/microsoftgraph/msgraph-sample-botframework/activity)

[Custom properties](https://github.com/microsoftgraph/msgraph-sample-botframework/custom-properties)

### Stars

[**8**\\
stars](https://github.com/microsoftgraph/msgraph-sample-botframework/stargazers)

### Watchers

[**7**\\
watching](https://github.com/microsoftgraph/msgraph-sample-botframework/watchers)

### Forks

[**9**\\
forks](https://github.com/microsoftgraph/msgraph-sample-botframework/forks)

[Report repository](https://github.com/contact/report-content?content_url=https%3A%2F%2Fgithub.com%2Fmicrosoftgraph%2Fmsgraph-sample-botframework&report=microsoftgraph+%28user%29)

## [Releases](https://github.com/microsoftgraph/msgraph-sample-botframework/releases)

No releases published

## [Packages\  0](https://github.com/orgs/microsoftgraph/packages?repo_name=msgraph-sample-botframework)

No packages published

## [Contributors\  5](https://github.com/microsoftgraph/msgraph-sample-botframework/graphs/contributors)

- [![@github-actions[bot]](https://avatars.githubusercontent.com/in/15368?s=64&v=4)](https://github.com/apps/github-actions)
- [![@dependabot[bot]](https://avatars.githubusercontent.com/in/29110?s=64&v=4)](https://github.com/apps/dependabot)
- [![@jasonjoh](https://avatars.githubusercontent.com/u/8966342?s=64&v=4)](https://github.com/jasonjoh)
- [![@microsoft-github-policy-service[bot]](https://avatars.githubusercontent.com/in/95686?s=64&v=4)](https://github.com/apps/microsoft-github-policy-service)
- [![@baywet](https://avatars.githubusercontent.com/u/7905502?s=64&v=4)](https://github.com/baywet)

## Languages

- [C#72.0%](https://github.com/microsoftgraph/msgraph-sample-botframework/search?l=c%23)
- [HTML28.0%](https://github.com/microsoftgraph/msgraph-sample-botframework/search?l=html)

You can’t perform that action at this time.
