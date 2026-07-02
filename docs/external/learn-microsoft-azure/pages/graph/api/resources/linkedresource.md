# linkedResource resource type

Namespace: microsoft.graph

Represents an item in a partner application related to a [todoTask](https://learn.microsoft.com/en-us/graph/api/resources/todotask?view=graph-rest-1.0). An example is an email from where the task was created. A **linkedResource** object stores information about that source application, and lets you link back to the related item. You can see the **linkedResource** in the task details view, as shown.

![Linked resource in task details pane](https://learn.microsoft.com/en-us/graph/images/todo-linkedresource-taskdetail.png)

Some **linkedResource** objects are not associated with any web URLs, in which case, the **webUrl** property is not required. For example, the linked item can be from a custom business app or native platform app, such as an SMS app on a mobile phone. The following is how a **linkedResource** appears with and without a URL.

![Linked resource with and without URL](https://learn.microsoft.com/en-us/graph/images/todo-linkedresource.png)

## Methods

| Method | Return type | Description |
| --- | --- | --- |
| [List](https://learn.microsoft.com/en-us/graph/api/todotask-list-linkedresources?view=graph-rest-1.0) | [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) collection | Get the linkedResources from the linkedResources navigation property. |
| [Create](https://learn.microsoft.com/en-us/graph/api/todotask-post-linkedresources?view=graph-rest-1.0) | [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) | Create a new linkedResources object. |
| [Get](https://learn.microsoft.com/en-us/graph/api/linkedresource-get?view=graph-rest-1.0) | [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) | Read the properties and relationships of a [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) object. |
| [Update](https://learn.microsoft.com/en-us/graph/api/linkedresource-update?view=graph-rest-1.0) | [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) | Update the properties of a [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) object. |
| [Delete](https://learn.microsoft.com/en-us/graph/api/linkedresource-delete?view=graph-rest-1.0) | None | Delete a [linkedResource](https://learn.microsoft.com/en-us/graph/api/resources/linkedresource?view=graph-rest-1.0) object. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| applicationName | String | The app name of the source that sends the **linkedResource**. |
| displayName | String | The title of the **linkedResource**. |
| externalId | String | ID of the object that is associated with this task on the third-party/partner system. |
| id | String | Server generated ID for the **linkedResource**. Inherited from [entity](https://learn.microsoft.com/en-us/graph/api/resources/entity?view=graph-rest-1.0). |
| webUrl | String | Deep link to the **linkedResource**. |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.linkedResource",
  "applicationName": "String",
  "displayName": "String",
  "externalId": "String",
  "id": "String (identifier)",
  "webUrl": "String"
}
```

* * *
