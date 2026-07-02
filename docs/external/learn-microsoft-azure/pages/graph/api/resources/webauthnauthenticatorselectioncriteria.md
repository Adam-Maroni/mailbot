# webauthnAuthenticatorSelectionCriteria resource type

Namespace: microsoft.graph

Important

APIs under the `/beta` version in Microsoft Graph are subject to change. Use of these APIs in production applications is not supported. To determine whether an API is available in v1.0, use the **Version** selector.

Properties of WebAuthn Authenticators allowed to be used for authentication in Entra ID. For more information, see [Authenticator Selection Criteria](https://www.w3.org/TR/WebAuthn-2/#dictdef-authenticatorselectioncriteria).

## Properties

| Property | Type | Description |
| --- | --- | --- |
| authenticatorAttachment | String | Microsoft Entra ID-preferred attachment modality. For more information, see [Authenticator Attachment Modality](https://www.w3.org/TR/WebAuthn-2/#authenticator-attachment-modality) |
| requireResidentKey | Boolean | Microsoft Entra ID-preferred client-side credential discoverability. Currently always `true`. The WebAuthn authenticator must store the credential identifier on the authenticator. |
| userVerification | String | Microsoft Entra ID requirement to verify the user is present during credential provisioning. Currently always `required`. |

## Relationships

None.

## JSON representation

The following JSON representation shows the resource type.

JSON

Copy

```json
{
  "@odata.type": "#microsoft.graph.webauthnAuthenticatorSelectionCriteria",
  "authenticatorAttachment": "String",
  "requireResidentKey": "Boolean",
  "userVerification": "String"
}
```

* * *
