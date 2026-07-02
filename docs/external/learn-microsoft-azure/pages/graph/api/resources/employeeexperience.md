# employeeExperience resource type

Namespace: microsoft.graph

Represents a container that exposes navigation properties for employee experience resources.

## Methods

| Method | Return type | Description |
| --- | --- | --- |
| [List communities](https://learn.microsoft.com/en-us/graph/api/employeeexperience-list-communities?view=graph-rest-1.0) | [community](https://learn.microsoft.com/en-us/graph/api/resources/community?view=graph-rest-1.0) collection | Get a list of the Viva Engage [community](https://learn.microsoft.com/en-us/graph/api/resources/community?view=graph-rest-1.0) objects and their properties. |
| [Create community](https://learn.microsoft.com/en-us/graph/api/employeeexperience-post-communities?view=graph-rest-1.0) | [community](https://learn.microsoft.com/en-us/graph/api/resources/community?view=graph-rest-1.0) | Create a new [community](https://learn.microsoft.com/en-us/graph/api/resources/community?view=graph-rest-1.0) in Viva Engage. |
| [List learningProviders](https://learn.microsoft.com/en-us/graph/api/employeeexperience-list-learningproviders?view=graph-rest-1.0) | [learningProvider](https://learn.microsoft.com/en-us/graph/api/resources/learningprovider?view=graph-rest-1.0) collection | Get a list of the [learningProvider](https://learn.microsoft.com/en-us/graph/api/resources/learningprovider?view=graph-rest-1.0) resources registered in Viva Learning for a tenant. |
| [Create learningProvider](https://learn.microsoft.com/en-us/graph/api/employeeexperience-post-learningproviders?view=graph-rest-1.0) | [learningProvider](https://learn.microsoft.com/en-us/graph/api/resources/learningprovider?view=graph-rest-1.0) | Create a new [learningProvider](https://learn.microsoft.com/en-us/graph/api/resources/learningprovider?view=graph-rest-1.0) object and register it with Viva Learning using the specified display name and logos for different themes. |
| [List roles](https://learn.microsoft.com/en-us/graph/api/employeeexperience-list-roles?view=graph-rest-1.0) | [engagementRole](https://learn.microsoft.com/en-us/graph/api/resources/engagementrole?view=graph-rest-1.0) collection | Get a list of all the [roles](https://learn.microsoft.com/en-us/graph/api/resources/engagementrole?view=graph-rest-1.0) that can be assigned in Viva Engage. |

## Properties

None.

## Relationships

| Relationship | Type | Description |
| --- | --- | --- |
| communities | [community](https://learn.microsoft.com/en-us/graph/api/resources/community?view=graph-rest-1.0) collection | A collection of communities in Viva Engage. |
| engagementAsyncOperations | [engagementAsyncOperation](https://learn.microsoft.com/en-us/graph/api/resources/engagementasyncoperation?view=graph-rest-1.0) collection | A collection of long-running, asynchronous operations related to Viva Engage. |
| learningProviders | [learningProvider](https://learn.microsoft.com/en-us/graph/api/resources/learningprovider?view=graph-rest-1.0) collection | A collection of learning providers. |
| roles | [engagementRole](https://learn.microsoft.com/en-us/graph/api/resources/engagementrole?view=graph-rest-1.0) collection | A collection of roles in Viva Engage. |

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.employeeExperience"
}
```

* * *
