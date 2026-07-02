# List cloudCertificationAuthorityLeafCertificates

Namespace: microsoft.graph

> **Important:** Microsoft supports Intune /beta APIs, but they are subject to more frequent change. Microsoft recommends using version v1.0 when possible. Check an API's availability in version v1.0 using the Version selector.

> **Note:** The Microsoft Graph API for Intune requires an [active Intune license](https://go.microsoft.com/fwlink/?linkid=839381) for the tenant.

List properties and relationships of the [cloudCertificationAuthorityLeafCertificate](https://learn.microsoft.com/en-us/graph/api/resources/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate?view=graph-rest-beta) objects.

This API is available in the following [national cloud deployments](https://learn.microsoft.com/en-us/graph/deployments).

| Global service | US Government L4 | US Government L5 (DOD) | China operated by 21Vianet |
| --- | --- | --- | --- |
| ✅ | ✅ | ✅ | ✅ |

## Permissions

One of the following permissions is required to call this API. To learn more, including how to choose permissions, see [Permissions](https://learn.microsoft.com/en-us/graph/permissions-reference).

| Permission type | Permissions (from least to most privileged) |
| --- | --- |
| Delegated (work or school account) | DeviceManagementConfiguration.Read.All, DeviceManagementConfiguration.ReadWrite.All |
| Delegated (personal Microsoft account) | Not supported. |
| Application | DeviceManagementConfiguration.Read.All, DeviceManagementConfiguration.ReadWrite.All |

## HTTP Request

HTTP

Copy

```http
GET /deviceManagement/cloudCertificationAuthorityLeafCertificate
GET /deviceManagement/cloudCertificationAuthority/{cloudCertificationAuthorityId}/cloudCertificationAuthorityLeafCertificate
```

## Request headers

| Header | Value |
| --- | --- |
| Authorization | Bearer {token}. Required. Learn more about [authentication and authorization](https://learn.microsoft.com/en-us/graph/auth/auth-concepts). |
| Accept | application/json |

## Request body

Do not supply a request body for this method.

## Response

If successful, this method returns a `200 OK` response code and a collection of [cloudCertificationAuthorityLeafCertificate](https://learn.microsoft.com/en-us/graph/api/resources/intune-cloudpkigraphservice-cloudcertificationauthorityleafcertificate?view=graph-rest-beta) objects in the response body.

## Example

### Request

Here is an example of the request.

HTTP

Copy

```http
GET https://graph.microsoft.com/beta/deviceManagement/cloudCertificationAuthorityLeafCertificate
```

### Response

Here is an example of the response. Note: The response object shown here may be truncated for brevity. All of the properties will be returned from an actual call.

HTTP

Copy

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 1206

{
  "value": [\
    {\
      "@odata.type": "#microsoft.graph.cloudCertificationAuthorityLeafCertificate",\
      "id": "976c94f8-94f8-976c-f894-6c97f8946c97",\
      "subjectName": "Subject Name value",\
      "issuerId": "Issuer Id value",\
      "issuerName": "Issuer Name value",\
      "certificateStatus": "active",\
      "validityStartDateTime": "2016-12-31T23:59:36.3292251-08:00",\
      "validityEndDateTime": "2016-12-31T23:57:06.8876616-08:00",\
      "crlDistributionPointUrl": "https://example.com/crlDistributionPointUrl/",\
      "certificationAuthorityIssuerUri": "Certification Authority Issuer Uri value",\
      "ocspResponderUri": "Ocsp Responder Uri value",\
      "thumbprint": "Thumbprint value",\
      "serialNumber": "Serial Number value",\
      "revocationDateTime": "2017-01-01T00:00:26.0037365-08:00",\
      "deviceName": "Device Name value",\
      "userPrincipalName": "User Principal Name value",\
      "deviceId": "Device Id value",\
      "userId": "User Id value",\
      "devicePlatform": "Device Platform value",\
      "keyUsages": [\
        "Key Usages value"\
      ],\
      "extendedKeyUsages": [\
        "Extended Key Usages value"\
      ]\
    }\
  ]
}
```

* * *
