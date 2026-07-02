# Create contact

Namespace: microsoft.graph

Add a contact to the root Contacts folder or to the contacts endpoint of another contact folder.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

One of the following permissions is required to call this API. To learn more, including how to choose permissions, see [Permissions](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Permissions (from least to most privileged) |
| --- | --- |
| Delegated (work or school account) | Contacts.ReadWrite |
| Delegated (personal Microsoft account) | Contacts.ReadWrite |
| Application | Contacts.ReadWrite |

## HTTP request

HTTP

Copy

```http
POST /me/contacts
POST /users/{id | userPrincipalName}/contacts
POST /me/contactFolders/{contactFolderId}/contacts
POST /users/{id | userPrincipalName}/contactFolders/{contactFolderId}/contacts
```

## Request headers

| Header | Value |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Content-Type | application/json |

## Request body

In the request body, supply a JSON representation of [contact](https://learn.microsoft.com/en-us/graph/api/resources/contact?view=graph-rest-1.0) object.

## Response

If successful, this method returns `201 Created` response code and [contact](https://learn.microsoft.com/en-us/graph/api/resources/contact?view=graph-rest-1.0) object in the response body.

## Example

### Request

The following example shows a request.

- [HTTP](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_http)
- [C#](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_csharp)
- [Go](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_go)
- [Java](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_java)
- [JavaScript](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_javascript)
- [PHP](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_php)
- [PowerShell](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_powershell)
- [Python](https://learn.microsoft.com/en-us/graph/api/user-post-contacts?view=graph-rest-1.0&tabs=http#tabpanel_1_python)

HTTP

Copy

```http
POST https://graph.microsoft.com/v1.0/me/contacts
Content-type: application/json

{
  "givenName": "Pavel",
  "surname": "Bansky",
  "emailAddresses": [\
    {\
      "address": "pavelb@contoso.com",\
      "name": "Pavel Bansky"\
    }\
  ],
  "businessPhones": [\
    "+1 732 555 0102"\
  ]
}
```

C#

Copy

```csharp

// Code snippets are only available for the latest version. Current version is 5.x

// Dependencies
using Microsoft.Graph.Models;

var requestBody = new Contact
{
	GivenName = "Pavel",
	Surname = "Bansky",
	EmailAddresses = new List<EmailAddress>
	{
		new EmailAddress
		{
			Address = "pavelb@contoso.com",
			Name = "Pavel Bansky",
		},
	},
	BusinessPhones = new List<string>
	{
		"+1 732 555 0102",
	},
};

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=csharp
var result = await graphClient.Me.Contacts.PostAsync(requestBody);
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
	  graphmodels "github.com/microsoftgraph/msgraph-sdk-go/models"
	  //other-imports
)

requestBody := graphmodels.NewContact()
givenName := "Pavel"
requestBody.SetGivenName(&givenName)
surname := "Bansky"
requestBody.SetSurname(&surname)

emailAddress := graphmodels.NewEmailAddress()
address := "pavelb@contoso.com"
emailAddress.SetAddress(&address)
name := "Pavel Bansky"
emailAddress.SetName(&name)

emailAddresses := []graphmodels.EmailAddressable {
	emailAddress,
}
requestBody.SetEmailAddresses(emailAddresses)
businessPhones := []string {
	"+1 732 555 0102",
}
requestBody.SetBusinessPhones(businessPhones)

// To initialize your graphClient, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=go
contacts, err := graphClient.Me().Contacts().Post(context.Background(), requestBody, nil)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Java

Copy

```java

// Code snippets are only available for the latest version. Current version is 6.x

GraphServiceClient graphClient = new GraphServiceClient(requestAdapter);

Contact contact = new Contact();
contact.setGivenName("Pavel");
contact.setSurname("Bansky");
LinkedList<EmailAddress> emailAddresses = new LinkedList<EmailAddress>();
EmailAddress emailAddress = new EmailAddress();
emailAddress.setAddress("pavelb@contoso.com");
emailAddress.setName("Pavel Bansky");
emailAddresses.add(emailAddress);
contact.setEmailAddresses(emailAddresses);
LinkedList<String> businessPhones = new LinkedList<String>();
businessPhones.add("+1 732 555 0102");
contact.setBusinessPhones(businessPhones);
Contact result = graphClient.me().contacts().post(contact);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

JavaScript

Copy

```javascript

const options = {
	authProvider,
};

const client = Client.init(options);

const contact = {
  givenName: 'Pavel',
  surname: 'Bansky',
  emailAddresses: [\
    {\
      address: 'pavelb@contoso.com',\
      name: 'Pavel Bansky'\
    }\
  ],
  businessPhones: [\
    '+1 732 555 0102'\
  ]
};

await client.api('/me/contacts')
	.post(contact);
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PHP

Copy

```php

<?php
use Microsoft\Graph\GraphServiceClient;
use Microsoft\Graph\Generated\Models\Contact;
use Microsoft\Graph\Generated\Models\EmailAddress;

$graphServiceClient = new GraphServiceClient($tokenRequestContext, $scopes);

$requestBody = new Contact();
$requestBody->setGivenName('Pavel');
$requestBody->setSurname('Bansky');
$emailAddressesEmailAddress1 = new EmailAddress();
$emailAddressesEmailAddress1->setAddress('pavelb@contoso.com');
$emailAddressesEmailAddress1->setName('Pavel Bansky');
$emailAddressesArray []= $emailAddressesEmailAddress1;
$requestBody->setEmailAddresses($emailAddressesArray);

$requestBody->setBusinessPhones(['+1 732 555 0102', ]);

$result = $graphServiceClient->me()->contacts()->post($requestBody)->wait();
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

PowerShell

Copy

```powershell

Import-Module Microsoft.Graph.PersonalContacts

$params = @{
	givenName = "Pavel"
	surname = "Bansky"
	emailAddresses = @(
		@{
			address = "pavelb@contoso.com"
			name = "Pavel Bansky"
		}
	)
	businessPhones = @(
	"+1 732 555 0102"
)
}

# A UPN can also be used as -UserId.
New-MgUserContact -UserId $userId -BodyParameter $params
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

Python

Copy

```python

# Code snippets are only available for the latest version. Current version is 1.x
from msgraph import GraphServiceClient
from msgraph.generated.models.contact import Contact
from msgraph.generated.models.email_address import EmailAddress
# To initialize your graph_client, see https://learn.microsoft.com/en-us/graph/sdks/create-client?from=snippets&tabs=python
request_body = Contact(
	given_name = "Pavel",
	surname = "Bansky",
	email_addresses = [\
		EmailAddress(\
			address = "pavelb@contoso.com",\
			name = "Pavel Bansky",\
		),\
	],
	business_phones = [\
		"+1 732 555 0102",\
	],
)

result = await graph_client.me.contacts.post(request_body)
```

> For details about how to [add the SDK](https://learn.microsoft.com/en-us/graph/sdks/sdk-installation) to your project and [create an authProvider](https://learn.microsoft.com/en-us/graph/sdks/choose-authentication-providers) instance, see the [SDK documentation](https://learn.microsoft.com/en-us/graph/sdks/sdks-overview).

### Response

The following example shows the response.

> **Note:** The response object shown here might be shortened for readability.

HTTP

Copy

```http
HTTP/1.1 201 Created
Content-type: application/json

{
  "id": "id-value",
  "createdDateTime": "2015-11-09T02:14:32Z",
  "lastModifiedDateTime": "2015-11-09T02:14:32Z",
   "displayName": "Pavel Bansky"
}
```

* * *
