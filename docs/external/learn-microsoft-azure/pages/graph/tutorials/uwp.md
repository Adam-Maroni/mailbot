# Microsoft Graph sample UWP app

[Permalink: Microsoft Graph sample UWP app](https://github.com/microsoftgraph/msgraph-sample-uwp#microsoft-graph-sample-uwp-app)

[![MSBuild](https://github.com/microsoftgraph/msgraph-training-uwp/actions/workflows/msbuild.yml/badge.svg)](https://github.com/microsoftgraph/msgraph-training-uwp/actions/workflows/msbuild.yml)![License.](https://camo.githubusercontent.com/8bb50fd2278f18fc326bf71f6e88ca8f884f72f179d3e555e20ed30157190d0d/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f6c6963656e73652d4d49542d677265656e2e737667)

This sample demonstrates how to use the Microsoft Graph .NET SDK to access data in Office 365 from UWP apps.

## Prerequisites

[Permalink: Prerequisites](https://github.com/microsoftgraph/msgraph-sample-uwp#prerequisites)

To run the completed project in this folder, you need the following:

- [Visual Studio](https://visualstudio.microsoft.com/vs/) installed on your development machine. If you do not have Visual Studio, visit the previous link for download options. ( **Note:** This tutorial was written with Visual Studio 2022 version 17.3.5. The steps in this guide may work with other versions, but that has not been tested.)
- Either a personal Microsoft account with a mailbox on Outlook.com, or a Microsoft work or school account.

If you don't have a Microsoft account, there are a couple of options to get a free account:

- You can [sign up for a new personal Microsoft account](https://signup.live.com/signup?wa=wsignin1.0&rpsnv=12&ct=1454618383&rver=6.4.6456.0&wp=MBI_SSL_SHARED&wreply=https://mail.live.com/default.aspx&id=64855&cbcxt=mai&bk=1454618383&uiflavor=web&uaid=b213a65b4fdc484382b6622b3ecaa547&mkt=E-US&lc=1033&lic=1).
- You can [sign up for the Microsoft 365 Developer Program](https://developer.microsoft.com/microsoft-365/dev-program) to get a free Microsoft 365 subscription.

## Register a native application with the Azure Active Directory admin center

[Permalink: Register a native application with the Azure Active Directory admin center](https://github.com/microsoftgraph/msgraph-sample-uwp#register-a-native-application-with-the-azure-active-directory-admin-center)

1. Open a browser and navigate to the [Azure Active Directory admin center](https://aad.portal.azure.com/) and login using a **personal account** (aka: Microsoft Account) or **Work or School Account**.

2. Select **Azure Active Directory** in the left-hand navigation, then select **App registrations** under **Manage**.

3. Select **New registration**. On the **Register an application** page, set the values as follows.
   - Set **Name** to `UWP Graph Sample`.
   - Set **Supported account types** to **Accounts in any organizational directory and personal Microsoft accounts**.
   - Under **Redirect URI**, change the dropdown to **Public client (mobile & desktop)**, and set the value to `https://login.microsoftonline.com/common/oauth2/nativeclient`.
4. Choose **Register**. On the **UWP Graph Tutorial** page, copy the value of the **Application (client) ID** and save it, you will need it in the next step.

## Configure the sample

[Permalink: Configure the sample](https://github.com/microsoftgraph/msgraph-sample-uwp#configure-the-sample)

1. Rename the OAuth.resw.example file to OAuth.resw.
2. Open `graph-tutorial.sln` in Visual Studio.
3. Edit the `OAuth.resw` file in visual studio. Replace `YOUR_APP_ID_HERE` with the **Application Id** you got from the App Registration Portal.
4. In Solution Explorer, right-click the **graph-tutorial** solution and choose **Restore NuGet Packages**.

## Run the sample

[Permalink: Run the sample](https://github.com/microsoftgraph/msgraph-sample-uwp#run-the-sample)

In Visual Studio, press **F5** or choose **Debug > Start Debugging**.

## Code of conduct

[Permalink: Code of conduct](https://github.com/microsoftgraph/msgraph-sample-uwp#code-of-conduct)

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Disclaimer

[Permalink: Disclaimer](https://github.com/microsoftgraph/msgraph-sample-uwp#disclaimer)

**THIS CODE IS PROVIDED _AS IS_ WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING ANY IMPLIED WARRANTIES OF FITNESS FOR A PARTICULAR PURPOSE, MERCHANTABILITY, OR NON-INFRINGEMENT.**

## About

This sample demonstrates how to use the Microsoft Graph .NET SDK to access data in Office 365 from UWP apps.

### Topics

[uwp](https://github.com/topics/uwp "Topic: uwp") [microsoft-graph](https://github.com/topics/microsoft-graph "Topic: microsoft-graph") [devxsample](https://github.com/topics/devxsample "Topic: devxsample")

### Resources

[Readme](https://github.com/microsoftgraph/msgraph-sample-uwp#readme-ov-file)

### License

[MIT license](https://github.com/microsoftgraph/msgraph-sample-uwp#MIT-1-ov-file)

### Code of conduct

[Code of conduct](https://github.com/microsoftgraph/msgraph-sample-uwp#coc-ov-file)

### Security policy

[Security policy](https://github.com/microsoftgraph/msgraph-sample-uwp#security-ov-file)

### Uh oh!

There was an error while loading. [Please reload this page](https://github.com/microsoftgraph/msgraph-sample-uwp).

[Activity](https://github.com/microsoftgraph/msgraph-sample-uwp/activity)

[Custom properties](https://github.com/microsoftgraph/msgraph-sample-uwp/custom-properties)

### Stars

[**30**\\
stars](https://github.com/microsoftgraph/msgraph-sample-uwp/stargazers)

### Watchers

[**6**\\
watching](https://github.com/microsoftgraph/msgraph-sample-uwp/watchers)

### Forks

[**15**\\
forks](https://github.com/microsoftgraph/msgraph-sample-uwp/forks)

[Report repository](https://github.com/contact/report-content?content_url=https%3A%2F%2Fgithub.com%2Fmicrosoftgraph%2Fmsgraph-sample-uwp&report=microsoftgraph+%28user%29)

## [Releases\  1](https://github.com/microsoftgraph/msgraph-sample-uwp/releases)

[Quick start zip 1.3\\
Latest\\
\\
on Jun 29, 2021Jun 29, 2021](https://github.com/microsoftgraph/msgraph-sample-uwp/releases/tag/1.3)

## [Packages\  0](https://github.com/orgs/microsoftgraph/packages?repo_name=msgraph-sample-uwp)

No packages published

### Uh oh!

There was an error while loading. [Please reload this page](https://github.com/microsoftgraph/msgraph-sample-uwp).

## [Contributors\  11](https://github.com/microsoftgraph/msgraph-sample-uwp/graphs/contributors)

- [![@jasonjoh](https://avatars.githubusercontent.com/u/8966342?s=64&v=4)](https://github.com/jasonjoh)
- [![@andrewconnell](https://avatars.githubusercontent.com/u/2068657?s=64&v=4)](https://github.com/andrewconnell)
- [![@github-actions[bot]](https://avatars.githubusercontent.com/in/15368?s=64&v=4)](https://github.com/apps/github-actions)
- [![@dependabot[bot]](https://avatars.githubusercontent.com/in/29110?s=64&v=4)](https://github.com/apps/dependabot)
- [![@juliemturner](https://avatars.githubusercontent.com/u/7570936?s=64&v=4)](https://github.com/juliemturner)
- [![@jthake](https://avatars.githubusercontent.com/u/6786616?s=64&v=4)](https://github.com/jthake)
- [![@dodaromike](https://avatars.githubusercontent.com/u/111081254?s=64&v=4)](https://github.com/dodaromike)
- [![@sbovo](https://avatars.githubusercontent.com/u/10991852?s=64&v=4)](https://github.com/sbovo)
- [![@microsoft-github-policy-service[bot]](https://avatars.githubusercontent.com/in/95686?s=64&v=4)](https://github.com/apps/microsoft-github-policy-service)
- [![@yinaa](https://avatars.githubusercontent.com/u/122239?s=64&v=4)](https://github.com/yinaa)
- [![@baywet](https://avatars.githubusercontent.com/u/7905502?s=64&v=4)](https://github.com/baywet)

## Languages

- [C#100.0%](https://github.com/microsoftgraph/msgraph-sample-uwp/search?l=c%23)

You can’t perform that action at this time.
