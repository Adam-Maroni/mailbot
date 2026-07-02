# Add user authentication to TypeScript apps for Microsoft Graph

In this article, you add user authentication to the application you created in [Build TypeScript apps with Microsoft Graph](https://learn.microsoft.com/en-us/graph/tutorials/typescript). You then use the Microsoft Graph user API to get the authenticated user.

## Add user authentication

The [Azure Identity client library for JavaScript](https://www.npmjs.com/package/@azure/identity) provides many `TokenCredential` classes that implement OAuth2 token flows. The [Microsoft Graph JavaScript client library](https://www.npmjs.com/package/@microsoft/microsoft-graph-client) uses those classes to authenticate calls to Microsoft Graph.

### Configure Graph client for user authentication

Start by using the `DeviceCodeCredential` class to request an access token by using the [device code flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-device-code).

1. Open **graphHelper.ts** and replace its contents with the following.

    TypeScript

Copy

```typescript
import 'isomorphic-fetch';
import {
     DeviceCodeCredential,
     DeviceCodePromptCallback,
} from '@azure/identity';
import { Client, PageCollection } from '@microsoft/microsoft-graph-client';
import { User, Message } from '@microsoft/microsoft-graph-types';
// prettier-ignore
import { TokenCredentialAuthenticationProvider } from
     '@microsoft/microsoft-graph-client/authProviders/azureTokenCredentials/index.js';

import { AppSettings } from './appSettings.js';

let _settings: AppSettings | undefined = undefined;
let _deviceCodeCredential: DeviceCodeCredential | undefined = undefined;
let _userClient: Client | undefined = undefined;

export function initializeGraphForUserAuth(
     settings: AppSettings,
     deviceCodePrompt: DeviceCodePromptCallback,
) {
     // Ensure settings isn't null
     if (!settings) {
       throw new Error('Settings cannot be undefined');
     }

     _settings = settings;

     _deviceCodeCredential = new DeviceCodeCredential({
       clientId: settings.clientId,
       tenantId: settings.tenantId,
       userPromptCallback: deviceCodePrompt,
     });

     const authProvider = new TokenCredentialAuthenticationProvider(
       _deviceCodeCredential,
       {
         scopes: settings.graphUserScopes,
       },
     );

     _userClient = Client.initWithMiddleware({
       authProvider: authProvider,
     });
}
```

2. Replace the empty `initializeGraph` function in **index.ts** with the following.

    TypeScript

Copy

```typescript
function initializeGraph(settings: AppSettings) {
     graphHelper.initializeGraphForUserAuth(settings, (info: DeviceCodeInfo) => {
       // Display the device code message to
       // the user. This tells them
       // where to go to sign in and provides the
       // code to use.
       console.log(info.message);
     });
}
```

This code declares two private properties, a `DeviceCodeCredential` object and a `Client` object. The `initializeGraphForUserAuth` function creates a new instance of `DeviceCodeCredential`, then uses that instance to create a new instance of `Client`. Every time an API call is made to Microsoft Graph through the `_userClient`, it uses the provided credential to get an access token.

### Test the DeviceCodeCredential

Next, add code to get an access token from the `DeviceCodeCredential`.

1. Add the following function to **graphHelper.ts**.

    TypeScript

Copy

```typescript
export async function getUserTokenAsync(): Promise<string> {
     // Ensure credential isn't undefined
     if (!_deviceCodeCredential) {
       throw new Error('Graph has not been initialized for user auth');
     }

     // Ensure scopes isn't undefined
     if (!_settings?.graphUserScopes) {
       throw new Error('Setting "scopes" cannot be undefined');
     }

     // Request token with given scopes
     const response = await _deviceCodeCredential.getToken(
       _settings?.graphUserScopes,
     );
     return response.token;
}
```

2. Replace the empty `displayAccessTokenAsync` function in **index.ts** with the following.

    TypeScript

Copy

```typescript
async function displayAccessTokenAsync() {
     try {
       const userToken = await graphHelper.getUserTokenAsync();
       console.log(`User token: ${userToken}`);
     } catch (err) {
       console.log(`Error getting user access token: ${err}`);
     }
}
```

3. Run the following command in your CLI in the root of your project.

    Bash

Copy

```bash
npx ts-node index.ts
```

4. Enter `1` when prompted for an option. The application displays a URL and device code.

    Shell

Copy

```shell
TypeScript Graph Tutorial

[1] Display access token
[2] List my inbox
[3] Send mail
[4] Make a Graph call
[0] Exit

Select an option [1...4 / 0]: 1
To sign in, use a web browser to open the page https://microsoft.com/devicelogin and
enter the code RK987NX32 to authenticate.
```

5. Open a browser and browse to the URL displayed. Enter the provided code and sign in.

Important

Be mindful of any existing Microsoft 365 accounts that are logged into your browser when browsing to `https://microsoft.com/devicelogin`. Use browser features such as profiles, guest mode, or private mode to ensure that you authenticate as the account you intend to use for testing.

6. Once completed, return to the application to see the access token.

Tip

For validation and debugging purposes _only_, you can decode user access tokens (for work or school accounts only) using Microsoft's online token parser at [https://jwt.ms](https://jwt.ms/). Parsing your token can be useful if you encounter token errors when calling Microsoft Graph. For example, verifying that the `scp` claim in the token contains the expected Microsoft Graph permission scopes.

## Get user

Now that authentication is configured, you can make your first Microsoft Graph API call. Add code to get the authenticated user's name and email address.

1. Open **graphHelper.ts** and add the following function.

    TypeScript

Copy

```typescript
export async function getUserAsync(): Promise<User> {
     // Ensure client isn't undefined
     if (!_userClient) {
       throw new Error('Graph has not been initialized for user auth');
     }

     // Only request specific properties with .select()
     return _userClient
       .api('/me')
       .select(['displayName', 'mail', 'userPrincipalName'])
       .get();
}
```

2. Replace the empty `greetUserAsync` function in **index.ts** with the following.

    TypeScript

Copy

```typescript
async function greetUserAsync() {
     try {
       const user = await graphHelper.getUserAsync();
       console.log(`Hello, ${user?.displayName}!`);
       // For Work/school accounts, email is in mail property
       // Personal accounts, email is in userPrincipalName
       console.log(`Email: ${user?.mail ?? user?.userPrincipalName ?? ''}`);
     } catch (err) {
       console.log(`Error getting user: ${err}`);
     }
}
```

If you run the app now, after you sign in the app welcomes you by name.

Bash

Copy

```bash
Hello, Megan Bowen!
Email: MeganB@contoso.com
```

### Code explained

Consider the code in the `getUserAsync` function. It's only a few lines, but there are some key details to notice.

#### Accessing 'me'

The function passes `/me` to the `_userClient.api` request builder, which builds a request to the [Get user](https://learn.microsoft.com/en-us/graph/api/user-get) API. This API is accessible two ways:

HTTP

Copy

```http
GET /me
GET /users/{user-id}
```

In this case, the code calls the `GET /me` API endpoint. This endpoint is a shortcut method to get the authenticated user without knowing their user ID.

Because the `GET /me` API endpoint gets the authenticated user, it's only available to apps that use user authentication. App-only authentication apps can't access this endpoint.

#### Requesting specific properties

The function uses the `select` method on the request to specify the set of properties it needs. This method adds the [$select query parameter](https://learn.microsoft.com/en-us/graph/query-parameters#select-parameter) to the API call.

#### Strongly typed return type

The function returns a `User` object deserialized from the JSON response from the API. Because the code uses `select`, only the requested properties have values in the returned `User` object. All other properties have default values.

## Next step

[Read and send email](https://learn.microsoft.com/en-us/graph/tutorials/typescript-email)

* * *
