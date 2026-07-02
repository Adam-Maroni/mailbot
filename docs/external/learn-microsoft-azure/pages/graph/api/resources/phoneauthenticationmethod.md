# phoneAuthenticationMethod resource type

Namespace: microsoft.graph

Represents a phone number and type that's registered to a user, and whether it's configured for the user to sign in via SMS.

A phone has one of three types: mobile, alternate mobile, or office. A user can have one number registered for each type, and must have a mobile phone before an alternate mobile phone is added. When using a phone for multi-factor authentication (MFA) or self-service password reset (SSPR), the mobile phone is the default and the alternate mobile phone is the backup.

Primary mobile phones can be used for both SMS and voice calls, depending on the tenant settings.

An office phone can only receive voice calls, not SMS messages.

This is a derived type that inherits from the [authenticationMethod](https://learn.microsoft.com/en-us/graph/api/resources/authenticationmethod?view=graph-rest-1.0) resource type.

## Methods

| Method | Return Type | Description |
| --- | --- | --- |
| [List](https://learn.microsoft.com/en-us/graph/api/authentication-list-phonemethods?view=graph-rest-1.0) | [phoneAuthenticationMethod](https://learn.microsoft.com/en-us/graph/api/resources/phoneauthenticationmethod?view=graph-rest-1.0) | Read properties and relationships of all this user's phoneAuthenticationMethod objects. |
| [Get](https://learn.microsoft.com/en-us/graph/api/phoneauthenticationmethod-get?view=graph-rest-1.0) | [phoneAuthenticationMethod](https://learn.microsoft.com/en-us/graph/api/resources/phoneauthenticationmethod?view=graph-rest-1.0) | Read properties and relationships of the phoneAuthenticationMethod object for a user. |
| [Add](https://learn.microsoft.com/en-us/graph/api/authentication-post-phonemethods?view=graph-rest-1.0) | [phoneAuthenticationMethod](https://learn.microsoft.com/en-us/graph/api/resources/phoneauthenticationmethod?view=graph-rest-1.0) | Create a user's phoneAuthenticationMethod object. |
| [Update](https://learn.microsoft.com/en-us/graph/api/phoneauthenticationmethod-update?view=graph-rest-1.0) | None | Update the phoneAuthenticationMethod object for a user. |
| [Delete](https://learn.microsoft.com/en-us/graph/api/phoneauthenticationmethod-delete?view=graph-rest-1.0) | None | Delete the phoneAuthenticationMethod object for a user. |
| [Disable SMS sign-in](https://learn.microsoft.com/en-us/graph/api/phoneauthenticationmethod-disablesmssignin?view=graph-rest-1.0) | None | Turn off SMS sign-in for a user. |
| [Enable SMS sign-in](https://learn.microsoft.com/en-us/graph/api/phoneauthenticationmethod-enablesmssignin?view=graph-rest-1.0) | None | Turn on SMS sign-in for a user. |

## Properties

| Property | Type | Description |
| --- | --- | --- |
| id | String | The identifier of this phone registered to this user. Read-only. <br>The value of ID is one of the following:<br>- `b6332ec1-7057-4abe-9331-3d72feddfe41` \- where **phoneType** is `alternateMobile`.<br>- `e37fc753-ff3b-4958-9484-eaa9425c82bc` \- where **phoneType** is `office`.<br>- `3179e48a-750b-4051-897c-87b9720928f7` \- where **phoneType** is `mobile`. |
| phoneNumber | String | The phone number to text or call for authentication. Phone numbers use the format `+{country code} {number}x{extension}`, with extension optional. For example, `+1 5555551234` or `+1 5555551234x123` are valid. Numbers are rejected when creating or updating if they don't match the required format. |
| phoneType | authenticationPhoneType | The type of this phone. The possible values are: `mobile`, `alternateMobile`, or `office`. |
| smsSignInState | authenticationMethodSignInState | Whether a phone is ready to be used for SMS sign-in or not. The possible values are: `notSupported`, `notAllowedByPolicy`, `notEnabled`, `phoneNumberNotUnique`, `ready`, or `notConfigured`, `unknownFutureValue`. |

### authenticationPhoneType values

Phones can be of three types, the following are the possible values.

| Value | Description |
| --- | --- |
| mobile | A primary mobile phone, usable for SMS and voice calls. |
| alternateMobile | An alternate or backup mobile phone, usable only for voice calls. |
| office | An office phone or landline, usable only for voice calls. |

### authenticationMethodSignInState values

The SMS sign-in state property gives information about whether or not a phone number is ready for sign in via SMS. The following are the possible values.

| Value | Description |
| --- | --- |
| notSupported | Primary sign-in isn't supported on this authentication method. For example, sign-in can be enabled only on a user's primary mobile number but not the alternate number. |
| notAllowedByPolicy | This user isn't enabled by policy to use this method as a primary sign-in. |
| notConfigured | This user is enabled by policy to use this method as primary sign-in but needs to take further action to configure it. |
| phoneNumberNotUnique | This user attempted to set up a phone number as primary sign-in but the number wasn't unique and can't be used as a sign-in name. |
| ready | This authentication method is ready for use in primary sign-in. |
| notEnabled | This sign-in method isn't enabled |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.phoneAuthenticationMethod",
  "id": "String (identifier)",
  "phoneNumber": "String",
  "phoneType": "string",
  "smsSignInState": "string"
}
```

* * *
