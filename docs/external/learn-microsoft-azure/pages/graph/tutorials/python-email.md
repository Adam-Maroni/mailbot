# Add email capabilities to Python apps using Microsoft Graph

In this article, you extend the application you created in [Build Python apps with Microsoft Graph](https://learn.microsoft.com/en-us/graph/tutorials/python) with Microsoft Graph mail APIs. You use Microsoft Graph to list the user's inbox and send an email.

## List user's inbox

Start by listing messages in the user's email inbox.

1. Add the following function to **graph.py**.

    Python

Copy

```python
async def get_inbox(self):
       query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
           # Only request specific properties
           select=['from', 'isRead', 'receivedDateTime', 'subject'],
           # Get at most 25 results
           top=25,
           # Sort by received time, newest first
           orderby=['receivedDateTime DESC']
       )
       request_config = MessagesRequestBuilder.MessagesRequestBuilderGetRequestConfiguration(
           query_parameters= query_params
       )

       messages = await self.user_client.me.mail_folders.by_mail_folder_id('inbox').messages.get(
               request_configuration=request_config)
       return messages
```

2. Replace the empty `list_inbox` function in **main.py** with the following.

    Python

Copy

```python
async def list_inbox(graph: Graph):
       message_page = await graph.get_inbox()
       if message_page and message_page.value:
           # Output each message's details
           for message in message_page.value:
               print('Message:', message.subject)
               if (
                   message.from_ and
                   message.from_.email_address
               ):
                   print('  From:', message.from_.email_address.name or 'NONE')
               else:
                   print('  From: NONE')
               print('  Status:', 'Read' if message.is_read else 'Unread')
               print('  Received:', message.received_date_time)

           # If @odata.nextLink is present
           more_available = message_page.odata_next_link is not None
           print('\nMore messages available?', more_available, '\n')
```

3. Run the app, sign in, and choose option 2 to list your inbox.

    Bash

Copy

```bash
Please choose one of the following options:
0. Exit
1. Display access token
2. List my inbox
3. Send mail
4. Make a Graph call
2
Message: Updates from Ask HR and other communities
From: Contoso Demo on Yammer
Status: Read
Received: 2022-04-26T19:19:05Z
Message: Employee Initiative Thoughts
From: Patti Fernandez
Status: Read
Received: 2022-04-25T19:43:57Z
Message: Voice Mail (11 seconds)
From: Alex Wilber
Status: Unread
Received: 2022-04-22T19:43:23Z
Message: Our Spring Blog Update
From: Alex Wilber
Status: Unread
Received: 2022-04-19T22:19:02Z
Message: Atlanta Flight Reservation
From: Alex Wilber
Status: Unread
Received: 2022-04-19T15:15:56Z
Message: Atlanta Trip Itinerary - down time
From: Alex Wilber
Status: Unread
Received: 2022-04-18T14:24:16Z

...

More messages available? True
```

### get\_inbox explained

Consider the code in the `get_inbox` function.

#### Accessing well-known mail folders

The function builds a request to the [List messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages) API. Because it includes the `mail_folders.by_mail_folder_id('inbox')` request builder, the API only returns messages in the requested mail folder. In this case, because the inbox is a default, well-known folder inside a user's mailbox, it's accessible via its well-known name. Nondefault folders are accessed the same way, by replacing the well-known name with the mail folder's ID property. For details on the available well-known folder names, see [mailFolder resource type](https://learn.microsoft.com/en-us/graph/api/resources/mailfolder).

#### Accessing a collection

Unlike the `get_user` function from the previous section, which returns a single object, this method returns a collection of messages. Most APIs in Microsoft Graph that return a collection don't return all available results in a single response. Instead, they use [paging](https://learn.microsoft.com/en-us/graph/paging) to return a portion of the results while providing a method for clients to request the next page.

##### Default page sizes

APIs that use paging implement a default page size. For messages, the default value is 10. Clients can request more (or less) by using the [$top](https://learn.microsoft.com/en-us/graph/query-parameters#top-parameter) query parameter. In `get_inbox`, adding `$top` is accomplished with the `top` parameter in the `MessagesRequestBuilderGetQueryParameters` object.

The value passed in `$top` is an upper-bound, not an explicit number. The API returns a number of messages _up to_ the specified value.

##### Getting subsequent pages

If there are more results available on the server, collection responses include an `@odata.nextLink` property with an API URL to access the next page. The Python SDK provides the `odata_next_link` property on collection page objects. If this property is present, there are more results available.

#### Sorting collections

The function uses the [$orderby query parameter](https://learn.microsoft.com/en-us/graph/query-parameters#orderby-parameter) to request results sorted by the time the message is received (`receivedDateTime` property). It includes the `DESC` keyword so that messages received more recently are listed first. In `get_inbox`, adding `$orderby` is accomplished with the `orderby` parameter in the `MessagesRequestBuilderGetQueryParameters` object.

## Send mail

Now add the ability to send an email message as the authenticated user.

1. Add the following function to **graph.py**.

    Python

Copy

```python
async def send_mail(self, subject: str, body: str, recipient: str):
       message = Message()
       message.subject = subject

       message.body = ItemBody()
       message.body.content_type = BodyType.Text
       message.body.content = body

       to_recipient = Recipient()
       to_recipient.email_address = EmailAddress()
       to_recipient.email_address.address = recipient
       message.to_recipients = []
       message.to_recipients.append(to_recipient)

       request_body = SendMailPostRequestBody()
       request_body.message = message

       await self.user_client.me.send_mail.post(body=request_body)
```

2. Replace the empty `send_mail` function in **main.py** with the following.

    Python

Copy

```python
async def send_mail(graph: Graph):
       # Send mail to the signed-in user
       # Get the user for their email address
       user = await graph.get_user()
       if user:
           user_email = user.mail or user.user_principal_name

           await graph.send_mail('Testing Microsoft Graph', 'Hello world!', user_email or '')
           print('Mail sent.\n')
```

3. Run the app, sign in, and choose option 3 to send an email to yourself.

    Bash

Copy

```bash
Please choose one of the following options:
0. Exit
1. Display access token
2. List my inbox
3. Send mail
4. Make a Graph call
3
Mail sent.
```

If you're testing with a developer tenant from the [Microsoft 365 Developer Program](https://developer.microsoft.com/microsoft-365/dev-program), the email you send might not be delivered, and you might receive a nondelivery report. If you want to unblock sending mail from your tenant, contact support via the [Microsoft 365 admin center](https://admin.microsoft.com/).

4. To verify the message was received, choose option 2 to list your inbox.

### send\_mail explained

Consider the code in the `send_mail` function.

#### Sending mail

The function uses the `user_client.me.send_mail` request builder, which builds a request to the [Send mail](https://learn.microsoft.com/en-us/graph/api/user-sendmail) API.

#### Creating objects

Unlike the previous calls to Microsoft Graph that only read data, this call creates data. To create items with the client library, you create a dictionary representing the request payload, set the desired properties, then send it in the API call. Because the call is sending data, the `post` method is used instead of `get`.

## Next step

[Add additional Microsoft Graph APIs](https://learn.microsoft.com/en-us/graph/tutorials/python-extend-app)

* * *
