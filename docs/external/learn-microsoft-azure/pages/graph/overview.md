# Overview of Microsoft Graph

Microsoft Graph is the gateway to data and intelligence in Microsoft cloud services like Microsoft Entra and Microsoft 365. Use the wealth of data accessible through Microsoft Graph to build apps for organizations and consumers that interact with millions of users.

![Diagram that shows how Microsoft Graph API, Copilot connectors, and Data Connect power the Microsoft 365 platform.](https://learn.microsoft.com/en-us/graph/images/microsoft-graph-dataconnect-connectors-enhance.png)

## Data and services powering the Microsoft 365 platform

In the Microsoft 365 platform, three main components enable data access and flow:

- The **Microsoft Graph API** offers a single endpoint, `https://graph.microsoft.com`, to provide access to rich, people-centric data and insights in the Microsoft cloud, including Microsoft 365, Windows, and Enterprise Mobility + Security. Use REST APIs or SDKs to access the endpoint and build apps for Microsoft 365 scenarios. These scenarios span productivity, collaboration, education, people and workplace intelligence, and more. Microsoft Graph also includes a powerful set of services that manage user and device identity, access, compliance, and security and help protect organizations from data leakage or loss.
- **[Microsoft 365 Copilot connectors](https://learn.microsoft.com/en-us/graph/overview#bring-data-from-an-external-content-source-to-microsoft-graph)** (formerly Microsoft Graph connectors) work in the incoming direction, delivering data external to the Microsoft cloud into Microsoft Graph services and applications to enhance Microsoft 365 experiences such as Microsoft Search. Connectors exist for many commonly used data sources such as Box, Google Drive, Jira, and Salesforce.
- **[Microsoft Graph Data Connect](https://learn.microsoft.com/en-us/graph/overview#access-microsoft-graph-data-at-scale)** provides a set of tools to streamline secure and scalable delivery of Microsoft Graph data to popular Azure data stores. The cached data serves as data sources for Azure development tools that you can use to build intelligent applications.

Together, the Microsoft Graph API, connectors, and Data Connect power the Microsoft 365 platform. With the ability to access Microsoft Graph data and other datasets, you can derive insights and analytics, extend Microsoft 365 experiences, and build unique, intelligent applications.

## What's in Microsoft Graph?

Microsoft Graph exposes REST APIs and client libraries to access data on the following Microsoft cloud services:

- **Microsoft 365 core services:** Bookings, Calendar, Excel, Microsoft Purview eDiscovery, Microsoft Search, OneDrive, OneNote, Outlook/Exchange, People (Outlook contacts), Planner, SharePoint, Teams, To Do, Viva Insights
- **Enterprise Mobility + Security services:** Advanced Threat Analytics, Advanced Threat Protection, Microsoft Entra, Identity Manager, and Intune
- **Windows services:** activities, devices, notifications, Universal Print
- **Dynamics 365 Business Central services**
- **Microsoft Partner Center services**

To find out more, see [Major services and features in Microsoft Graph](https://learn.microsoft.com/en-us/graph/overview-major-services).

![Diagram that shows the primary resources and relationships that are part of Microsoft Graph](https://learn.microsoft.com/en-us/graph/images/microsoft-graph.png)

## What can you do with Microsoft Graph?

Getting Started with Microsoft Graph - YouTube

Tap to unmute

[Getting Started with Microsoft Graph](https://www.youtube.com/watch?v=PI9NO5rayiY) [Microsoft 365 Developer](https://www.youtube-nocookie.com/channel/UCV_6HOhwxYLXAGd-JOqKPoQ)

![thumbnail-image](https://yt3.ggpht.com/UNxiZXILPC64OgmT6gbzBpTxXU87q1MGV7JTLWg4WgT2xddKTFmJBI_23ukLMPRRcV8VK-RzbrA=s68-c-k-c0x00ffffff-no-rj)

Microsoft 365 Developer43.2K subscribers

Use Microsoft Graph to build experiences around the user's unique context to help them be more productive. Imagine an app that...

- Looks at your next meeting and helps you prepare for it by providing profile information for attendees, including their job titles and managers, as well as information about the latest documents they're working on, and people they're collaborating with.
- Scans your calendar, and suggests the best times for the next team meeting.
- Fetches the latest sales projection chart from an Excel file in your OneDrive and lets you update the forecast in real time, all from your phone.
- Subscribes to changes in your calendar, sends you an alert when you're spending too much time in meetings, and provides recommendations for the ones you can miss or delegate based on how relevant the attendees are to you.
- Helps you sort out personal and work information on your phone; for example, by categorizing pictures that should go to your personal OneDrive and business receipts that should go to your OneDrive for Business.
- Analyzes at-scale Microsoft 365 data so that decision makers can unlock valuable insights into time allocation and collaboration patterns that improve business productivity.
- Brings custom business data into Microsoft Graph, indexing it to make it searchable along with data from Microsoft 365 services.

Pick the first scenario about researching meeting attendees as an example. With the Microsoft Graph API, you can:

1. Get the email addresses of the [meeting event](https://learn.microsoft.com/en-us/graph/api/resources/event) attendees.
2. Look them up individually as a [user](https://learn.microsoft.com/en-us/graph/api/resources/user) in Microsoft Entra ID to [get their profile information](https://learn.microsoft.com/en-us/graph/api/user-get).

You can then navigate to other resources using relationships:

- Connect to their manager through a [manager relationship](https://learn.microsoft.com/en-us/graph/api/user-list-manager).
- Get valuable insights and intelligence including the popular files [trending around](https://learn.microsoft.com/en-us/graph/api/resources/insights-trending) the user.
- [Get the most relevant people](https://learn.microsoft.com/en-us/graph/api/user-list-people?view=graph-rest-beta&preserve-view=true) around the user.
- Extend the scenario to get to the user's groups through a [memberOf](https://learn.microsoft.com/en-us/graph/api/user-list-memberof) relationship.
- [Reach other members in each group](https://learn.microsoft.com/en-us/graph/api/group-list-members).
- Tap into other scenarios enabled by [groups](https://learn.microsoft.com/en-us/graph/microsoft365-groups-concept-overview), such as [education](https://learn.microsoft.com/en-us/graph/education-concept-overview) and [teamwork](https://learn.microsoft.com/en-us/graph/teams-concept-overview).

To find out more, see [Integration patterns](https://learn.microsoft.com/en-us/graph/integration-patterns-overview).

Microsoft Graph is secured and only authorized callers can access the data. For more information, see [Authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts).

When you use Microsoft Graph APIs, you agree to the [Microsoft APIs Terms of Use](https://learn.microsoft.com/en-us/legal/microsoft-apis/terms-of-use?context=/graph/context) and the [Microsoft Privacy Statement](https://go.microsoft.com/fwlink/?LinkId=521839).

### Popular API requests

Check out some of these common scenarios for working with the Microsoft Graph API. The links take you to the [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer).

| **Operation** | **URL** |
| --- | --- |
| GET my profile | [`https://graph.microsoft.com/v1.0/me`](https://developer.microsoft.com/graph/graph-explorer/?request=me&version=v1.0) |
| GET my files | [`https://graph.microsoft.com/v1.0/me/drive/root/children`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fdrive%2Froot%2Fchildren&version=v1.0) |
| GET my photo | [`https://graph.microsoft.com/v1.0/me/photo/$value`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fphoto%2F%24value&version=v1.0) |
| GET my mail | [`https://graph.microsoft.com/v1.0/me/messages`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fmessages&version=v1.0) |
| GET my high importance email | [`https://graph.microsoft.com/v1.0/me/messages?$filter=importance%20eq%20'high'`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fmessages%3F%24filter%3Dimportance%2520eq%2520%27high%27&version=v1.0) |
| GET my calendar events | [`https://graph.microsoft.com/v1.0/me/events`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fevents&version=v1.0) |
| GET my manager | [`https://graph.microsoft.com/v1.0/me/manager`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fmanager&version=v1.0) |
| GET last user to modify file foo.txt | [`https://graph.microsoft.com/v1.0/me/drive/root/children/foo.txt/lastModifiedByUser`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fdrive%2Froot%2Fchildren%2Ffoo.txt%2FlastModifiedByUser&version=v1.0) |
| GET Microsoft 365 groups I'm a member of | [`https://graph.microsoft.com/v1.0/me/memberOf/$/microsoft.graph.group?$filter=groupTypes/any(a:a%20eq%20'unified')`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2FmemberOf%2F%24%2Fmicrosoft.graph.group%3F%24filter%3DgroupTypes%2Fany(a%3Aa%2520eq%2520%27unified%27)&version=v1.0) |
| GET users in my organization | [`https://graph.microsoft.com/v1.0/users`](https://developer.microsoft.com/graph/graph-explorer/?request=users&version=v1.0) |
| GET groups in my organization | [`https://graph.microsoft.com/v1.0/groups`](https://developer.microsoft.com/graph/graph-explorer/?request=groups&version=v1.0) |
| GET people related to me | [`https://graph.microsoft.com/v1.0/me/people`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fpeople&version=beta) |
| GET items trending around me | [`https://graph.microsoft.com/beta/me/insights/trending`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Finsights%2Ftrending&version=v1.0) |
| GET my notes | [`https://graph.microsoft.com/v1.0/me/onenote/notebooks`](https://developer.microsoft.com/graph/graph-explorer/?request=me%2Fonenote%2Fnotebooks&version=beta) |

## Bring data from an external content source to Microsoft Graph

Use [Copilot connectors](https://learn.microsoft.com/en-us/graph/connecting-external-content-connectors-overview) to bring data external to the Microsoft cloud into Microsoft Graph. Examples of such data can be an organization's human resources database or product catalog, hosted on-premises or in the public or private clouds.

Copilot connectors create connections to external data sources, index the data, and store it as external custom items and files. Once indexed, those items can show up in Microsoft Search and for apps that use the [Microsoft Search API](https://learn.microsoft.com/en-us/graph/search-concept-overview).

## Access Microsoft Graph data at scale

Use [Microsoft Graph Data Connect](https://learn.microsoft.com/en-us/graph/data-connect-concept-overview) to access data on Microsoft Graph at scale, while allowing administrators granular consent and full control over their Microsoft Graph data. Data Connect streamlines the delivery of this data to Microsoft Azure.

Using Azure tools, you can then build intelligent apps that:

- Find the closest subject-matter expert in your organization.
- Automate knowledge base creation.
- Analyze meeting requests to provide insights into conference room utilization.
- Detect fraud with productivity and communication data.

## When should I use Microsoft Graph API or Data Connect?

Microsoft Graph Data Connect lets you interact with data available through Microsoft Graph APIs. Data Connect provides tools to streamline building intelligent applications, all within the Microsoft cloud.

| **Feature** | **Microsoft Graph API** | **Microsoft Graph Data Connect** |
| --- | --- | --- |
| **Access scope** | Single user or entire tenant | Many users or groups |
| **Access pattern** | Real time | Recurrent schedule |
| **Data operations** | Operates on source data | Operates on a cache of the data |
| **Data protection** | Data is protected while in the source service like Microsoft 365 and Microsoft Entra | Data protection is extended to the cache of data in your Azure subscription |
| **User consent** | Self<br>Resource types | None |
| **Admin consent** | Entire organization<br>Resource types | Select groups of users<br>Resource types and properties<br>Excludes users |
| **Access tools** | RESTful web queries | Azure Data Factory |

## Try out a sample app

Use the [quickstart](https://developer.microsoft.com/graph/quick-start) to set up a ready-to-run sample app.

## Related content

- Try a sample request in the [Graph Explorer](https://developer.microsoft.com/graph/graph-explorer).
- Explore the [services and features](https://learn.microsoft.com/en-us/graph/overview-major-services) that you can use in your scenarios.
- Explore the [integration patterns](https://learn.microsoft.com/en-us/graph/integration-patterns-overview) that might apply to your scenario.
- See [what's new](https://learn.microsoft.com/en-us/graph/whats-new-overview) in Microsoft Graph.
- Learn about [metered APIs and services in Microsoft Graph](https://learn.microsoft.com/en-us/graph/metered-api-overview).
- Find out how to [get an auth token](https://learn.microsoft.com/en-us/graph/auth/auth-concepts) in your app.
- Start [using the API](https://learn.microsoft.com/en-us/graph/use-the-api).

* * *
