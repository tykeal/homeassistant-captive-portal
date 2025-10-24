<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
Note: Extracted reference material from TP-Link FAQ 3231 for internal development research; not a verbatim copy of full content.
-->
Welcome to Our Website! If you stay on our site, we and our third-party partners use cookies, pixels, and other tracking technologies to better understand how you use our site, provide and improve our services, and personalize your experience and ads based on your interests. Learn more in your privacy choices.

Okay

Table of Contents

# API and Code Sample for External Portal Server (Omada Controller 5.0.15 or above)

Knowledgebase

Configuration Guide

Portal

API

Bookmarks [Copy Link](https://support.omadanetworks.com/us/document/13080/)Feedback

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3ccircle%20cx='8'%20cy='8'%20r='5.96154'%20stroke='%232B2B2B'%20stroke-opacity='0.6'%20stroke-width='1.07692'/%3e%3cpath%20d='M8%204V8L10.5%2010'%20stroke='%232B2B2B'%20stroke-opacity='0.6'/%3e%3c/svg%3e)09-20-2024

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20fill-rule='evenodd'%20clip-rule='evenodd'%20d='M8%2013.1924C2.80769%2013.1924%200.5%208.00005%200.5%208.00005C0.5%208.00005%202.80769%202.80774%208%202.80774C13.1923%202.80774%2015.5%208.00005%2015.5%208.00005C15.5%208.00005%2013.1923%2013.1924%208%2013.1924ZM1.79499%207.7102C1.72995%207.81662%201.67332%207.91397%201.62499%208.00005C1.67332%208.08613%201.72995%208.18347%201.79499%208.2899C2.06569%208.73286%202.47566%209.32273%203.0299%209.90958C4.14007%2011.0851%205.76988%2012.1924%208%2012.1924C10.2301%2012.1924%2011.8599%2011.0851%2012.9701%209.90958C13.5243%209.32273%2013.9343%208.73286%2014.205%208.2899C14.27%208.18347%2014.3267%208.08613%2014.375%208.00005C14.3267%207.91397%2014.27%207.81662%2014.205%207.7102C13.9343%207.26723%2013.5243%206.67736%2012.9701%206.09052C11.8599%204.91504%2010.2301%203.80774%208%203.80774C5.76988%203.80774%204.14007%204.91504%203.0299%206.09052C2.47566%206.67736%202.06569%207.26723%201.79499%207.7102ZM9.88462%208.00053C9.88462%209.04137%209.04084%209.88515%208%209.88515C6.95916%209.88515%206.11539%209.04137%206.11539%208.00053C6.11539%206.95969%206.95916%206.11591%208%206.11591C9.04084%206.11591%209.88462%206.95969%209.88462%208.00053ZM10.8846%208.00053C10.8846%209.59366%209.59313%2010.8851%208%2010.8851C6.40687%2010.8851%205.11539%209.59366%205.11539%208.00053C5.11539%206.4074%206.40687%205.11591%208%205.11591C9.59313%205.11591%2010.8846%206.4074%2010.8846%208.00053Z'%20fill='%232B2B2B'%20fill-opacity='0.6'/%3e%3c/svg%3e)14882

**Suitable for Omada Controller 5.0.15 or above.**

**For Omada Controller 4.1.5 to 4.4.6, please refer to** [**FAQ 2907**](https://www.tp-link.com/support/faq/2907/)

**For Omada Controller 2.6.0 to 3.2.17, please refer to** [**FAQ 2274**](https://www.tp-link.com/support/faq/2274/)

Compared to Omada SDN Controller v4, the main changes are as follows:

1\. Add Controller ID to the URL for hotspot login and client information submission.

2\. Add the HTTP header, which carries the CSRF Token.

Note: The keywords in **_Bold Italics_** indicate parameters that are automatically ~~filled~~ populated by the EAP or Gateway and should be correctly identified and delivered by your External Portal Server. The meanings of the parameters are ~~stated~~ outlined in the ~~first appearance~~ chart later in this article.

This document outlines the requirements to establish an External Portal Server ( **Portal** for short). The picture below depicts the data flow among the network devices, which may help better understand the working mechanism.

![](https://static.tp-link.com/upload/faq/image-20240216122509-7_20240216202510l.jpeg)

**Steps 1 and 2.**

When a client is connected to the wireless or wired network with a Portal enabled and attempts to access the Internet, its HTTP request will be intercepted by the EAP or Gateway, respectively, and will then be redirected to the Omada SDN Controller ( **Controller** for short) along with the connection information that is populated automatically by the EAP or Gateway in the URL.

**Steps 3 and 4.**

Next, the client will send an **HTTP GET** request with the connection information to the Controller and be redirected to the Portal by the Controller’s reply with an HTTP response using status code 302. The HTTP response includes the Portal’s URL in the location field as well as the connection information.

URL for EAP:

http(s):// **_PORTAL?_** clientMac= **_CLIENT\_MAC_**&apMac= **_AP\_MAC_**&ssidName= **_SSID\_NAME_**&t= **_TIME\_SINCE\_EPOCH_**&radioId= **_RADIO\_ID_**&site= **_SITE\_NAME_**&redirectUrl= **_LANDING\_PAGE_**.

URL for Gateway:

http(s):// **_PORTAL?_** clientMac= **_CLIENT\_MAC_**&gatewayMac= **_GATEWAY\_MAC_**&vid= **_VLAN\_ID_**&t= **_TIME\_SINCE\_EPOCH_**&site= **_SITE\_NAME_**&redirectUrl= **_LANDING\_PAGE_**.

|     |     |     |
| --- | --- | --- |
| **_PORTAL_** | The IP address or URL, and Port number (if necessary) of the External Portal Server. |
| clientMac | **_CLIENT\_MAC_** | MAC address of the client. |
| apMac | **_AP\_MAC_** | MAC address of the EAP to which the client is connected. |
| gatewayMac | **_GATEWAY\_MAC_** | MAC address of the Gateway. |
| vid | **_VLAN\_ID_** | VLAN ID of the wired network to which the client is connected. |
| ssidName | **_SSID\_NAME_** | Name of the SSID to which the client is connected |
| radioId | **_RADIO\_ID_** | Radio ID of the band to which the client is connected, where 0 represents 2.4G and 1 represents 5G. |
| site | **_SITE\_NAME_** | Site name. |
| redirectUrl | **_LANDING\_PAGE_** | URL to visit after successful authentication, which can be set in the Landing Page. |
| t | **_TIME\_SINCE\_EPOCH_** | Unit here is microsecond. |

![https://static.tp-link.com/image-20210301141438-2_1614579303917s.png](https://static.tp-link.com/image-20210301141438-2_1614579303917s.png)

**Steps 5 and 6.**

The client will send an **HTTP GET** request to the Portal with the URL above. The Portal must be able to recognize and keep the connection information in the query string of the HTTP GET request and return the web page for authentication.

**Steps 7, 8 and 9.**

The client will submit authentication information to the Portal, which will be delivered to the authentication server, and be verified. Then, the authentication server returns the authentication result to the Portal.

_You can decide how the Portal obtains the client's authentication information and how the Portal communicates with the authentication server, depending to your specific network requirements, which is beyond the scope of this article._

**NOTE:** In the figure above, the Portal and authentication server are separated. You can install them on the same server if desired. The authentication method is also up to you. Just make sure the Portal is able to receive the authentication result from the authentication server.

**Steps 10 and 11.**

If the authentication request is authorized, the Portal should send the client information to the Controller by calling its API.

First, it must log in to the Controller by sending an **HTTP POST** request. The request’s URL should be https:// **_CONTROLLER_**: **_PORT_**/ **_CONTROLLER\_ID_**/api/v2/hotspot/login and it should carry the operator account information in **JSON format** in the HTTP message body: {"name": " **_OPERATOR\_USERNAME_**","password": " **_OPERATOR\_PASSWORD_**"}.

Note that the account and password here are the operator added in the hotspot manager interface, rather than the account and password for the controller account.

![](https://static.tp-link.com/upload/faq/image-20240216122509-8_20240216202510j.png)

|     |     |
| --- | --- |
| **_CONTROLLER_** | IP address or URL of Omada SDN Controller. |
| **_PORT_** | HTTPS Port for **Controller Management** of Omada SDN Controller (8043 for software, and 433 for OC by default, go to Settings --- Controller --- Access Config for modification). |
| **_CONTROLLER\_ID_** | Identifier of the Omada SDN Controller. When you access the controller, the identifier will be automatically added to the URL, from which you will get the identifier.<br>For example, if your controller URL is https://localhost:8043/abcdefghijklmnopqrstuvwxyzabcdef/, then the CONTROLLER\_ID is abcdefghijklmnopqrstuvwxyzabcdef. |
| **_OPERATOR\_USERNAME_** | Username of the hotspot operator. |
| **_OPERATOR\_PASSWORD_** | Password of the hotspot operator. |

PHP Code Template:

public static function login()

{

$loginInfo = array(

"name" => OPERATOR\_USER,

"password" => OPERATOR\_PASSWORD

);

$headers = array(

"Content-Type: application/json",

"Accept: application/json"

);

$ch = curl\_init();

**// post**

curl\_setopt($ch, CURLOPT\_POST, TRUE);

**// Set return to a value, not return to page**

curl\_setopt($ch, CURLOPT\_RETURNTRANSFER, 1);

**// Set up cookies. COOKIE\_FILE\_PATH defines where to save Cookie.**

curl\_setopt($ch, CURLOPT\_COOKIEJAR, COOKIE\_FILE\_PATH);

curl\_setopt($ch, CURLOPT\_COOKIEFILE, COOKIE\_FILE\_PATH);

**// Allow Self Signed Certs**

curl\_setopt($ch, CURLOPT\_SSL\_VERIFYPEER, FALSE);

curl\_setopt($ch, CURLOPT\_SSL\_VERIFYHOST, FALSE);

**// API Call**

curl\_setopt($ch, CURLOPT\_URL, "https://" . CONTROLLER . ":" . PORT . "/" . CONTROLLER\_ID . "/api/v2/hotspot/login");

curl\_setopt($ch, CURLOPT\_HTTPHEADER, $headers);

curl\_setopt($ch, CURLOPT\_POSTFIELDS, json\_encode($loginInfo));

$res = curl\_exec($ch);

$resObj = json\_decode($res);

**//Prevent CSRF. TOKEN\_FILE\_PATH defines where to save Token.**

if ($resObj->errorCode == 0) {

**// login successfully**

self::setCSRFToken($resObj->result->token);

}

curl\_close($ch);

}

private static function setCSRFToken($token)

{

$myfile = fopen(TOKEN\_FILE\_PATH, "w") or die("Unable to open file!");

fwrite($myfile, $token);

fclose($myfile);

return $token;

}

If the login authentication is successful, the Controller will reply with the following JSON in the HTTP body. Note that the token inside result is the CSRF-Token, which should be added to the HTTP Header of the following steps.

{

"errorCode": 0,

"msg": "Hotspot log in successfully.",

"result": {

"token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

}

}

**Steps 12 and 13.**

After successful login, Portal can send the client authentication result to https:// **_CONTROLLER_**: **_PORT_**/ **_CONTROLLER\_ID_**/api/v2/hotspot/extPortal/auth with **HTTP POST** method.

The client information should be encapsulated in **JSON format** in the HTTP message body, and must contain the following parameters.

For EAP: {"clientMac":" **_CLIENT\_MAC_**","apMac":" **_AP\_MAC_**","ssidName":" **_SSID\_NAME_**","radioId":" **_RADIO\_ID_**","site":" **_SITE\_NAME_**","time":" **_EXPIRE\_TIME_**","authType":" **_4_**"}

For Gateway:

{"clientMac":" **_CLIENT\_MAC_**","gatewayMac":" **_GATEWAY\_MAC_**","vid":" **_VLAN\_ID_** ","site":" **_SITE\_NAME_**","time":" **_EXPIRE\_TIME_**","authType":" **_4_**"}

|     |     |     |
| --- | --- | --- |
| time | **_EXPIRE\_TIME_** | Authentication Expiration time. Unit here is microsecond. |

PHP Code Template for EAP:

public static function authorize($clientMac, $apMac, $ssidName, $radioId, $milliseconds)

{

**// Send user to authorize and the time allowed**

$authInfo = array(

'clientMac' => $clientMac,

'apMac' => $apMac,

'ssidName' => $ssidName,

'radioId' => $radioId,

'time' => $milliseconds,

'authType' => 4

);

$csrfToken = self::getCSRFToken();

$headers = array(

'Content-Type: application/json',

'Accept: application/json',

'Csrf-Token: ' . $csrfToken

);

$ch = curl\_init();

**// post**

curl\_setopt($ch, CURLOPT\_POST, TRUE);

**// Set return to a value, not return to page**

curl\_setopt($ch, CURLOPT\_RETURNTRANSFER, 1);

**// Set up cookies.**

curl\_setopt($ch, CURLOPT\_COOKIEJAR, COOKIE\_FILE\_PATH);

curl\_setopt($ch, CURLOPT\_COOKIEFILE, COOKIE\_FILE\_PATH);

**// Allow Self Signed Certs**

curl\_setopt($ch, CURLOPT\_SSL\_VERIFYPEER, FALSE);

curl\_setopt($ch, CURLOPT\_SSL\_VERIFYHOST, FALSE);

**// API Call**

curl\_setopt($ch, CURLOPT\_URL, "https://" . CONTROLLER . ":" . PORT . "/" . CONTROLLER\_ID . "/api/v2/hotspot/login");

curl\_setopt($ch, CURLOPT\_POSTFIELDS, json\_encode($authInfo));

curl\_setopt($ch, CURLOPT\_HTTPHEADER, $headers);

$res = curl\_exec($ch);

echo $res;

$resObj = json\_decode($res);

if ($resObj->errorCode == 0) {

**// authorized successfully**

}

curl\_close($ch);

}

public static function getCSRFToken()

{

$myfile = fopen(TOKEN\_FILE\_PATH, "r") or die("Unable to open file!");

$token = fgets($myfile);

fclose($myfile);

return $token;

}

If the authentication request is accepted, the Controller will reply with the following JSON:

{

"errorCode": 0

}

**Note**: Portal should be able to meet the following two requirements:

1. **Allow self-signed certificate**. Or you will upload your own HTTPS certificate to Controller.

2\. Read and save the “ **TPEAP\_SESSIONID** **”** **in Cookie**, and send authentication request with the Cookie.

\\* For Controller v5.11 and above, the Cookie name is “ **TPOMADA\_SESSIONID**”.

Please Rate this Document

![](data:image/svg+xml,%3csvg%20width='32'%20height='32'%20viewBox='0%200%2032%2032'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20d='M15.4641%203.09019C15.6842%202.64424%2016.3201%202.64424%2016.5402%203.09019L20.4106%2010.9324L29.0649%2012.1899C29.5571%2012.2614%2029.7536%2012.8662%2029.3975%2013.2133L23.1351%2019.3176L24.6134%2027.937C24.6975%2028.4272%2024.1831%2028.8009%2023.7429%2028.5695L16.0022%2024.5L8.26148%2028.5695C7.8213%2028.8009%207.30685%2028.4272%207.39091%2027.937L8.86925%2019.3176L2.6069%2013.2133C2.25079%2012.8662%202.44729%2012.2614%202.93943%2012.1899L11.5938%2010.9324L15.4641%203.09019Z'%20fill='%231D2529'%20fill-opacity='0.24'/%3e%3c/svg%3e)![](data:image/svg+xml,%3csvg%20width='32'%20height='32'%20viewBox='0%200%2032%2032'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20d='M15.4641%203.09019C15.6842%202.64424%2016.3201%202.64424%2016.5402%203.09019L20.4106%2010.9324L29.0649%2012.1899C29.5571%2012.2614%2029.7536%2012.8662%2029.3975%2013.2133L23.1351%2019.3176L24.6134%2027.937C24.6975%2028.4272%2024.1831%2028.8009%2023.7429%2028.5695L16.0022%2024.5L8.26148%2028.5695C7.8213%2028.8009%207.30685%2028.4272%207.39091%2027.937L8.86925%2019.3176L2.6069%2013.2133C2.25079%2012.8662%202.44729%2012.2614%202.93943%2012.1899L11.5938%2010.9324L15.4641%203.09019Z'%20fill='%231D2529'%20fill-opacity='0.24'/%3e%3c/svg%3e)![](data:image/svg+xml,%3csvg%20width='32'%20height='32'%20viewBox='0%200%2032%2032'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20d='M15.4641%203.09019C15.6842%202.64424%2016.3201%202.64424%2016.5402%203.09019L20.4106%2010.9324L29.0649%2012.1899C29.5571%2012.2614%2029.7536%2012.8662%2029.3975%2013.2133L23.1351%2019.3176L24.6134%2027.937C24.6975%2028.4272%2024.1831%2028.8009%2023.7429%2028.5695L16.0022%2024.5L8.26148%2028.5695C7.8213%2028.8009%207.30685%2028.4272%207.39091%2027.937L8.86925%2019.3176L2.6069%2013.2133C2.25079%2012.8662%202.44729%2012.2614%202.93943%2012.1899L11.5938%2010.9324L15.4641%203.09019Z'%20fill='%231D2529'%20fill-opacity='0.24'/%3e%3c/svg%3e)![](data:image/svg+xml,%3csvg%20width='32'%20height='32'%20viewBox='0%200%2032%2032'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20d='M15.4641%203.09019C15.6842%202.64424%2016.3201%202.64424%2016.5402%203.09019L20.4106%2010.9324L29.0649%2012.1899C29.5571%2012.2614%2029.7536%2012.8662%2029.3975%2013.2133L23.1351%2019.3176L24.6134%2027.937C24.6975%2028.4272%2024.1831%2028.8009%2023.7429%2028.5695L16.0022%2024.5L8.26148%2028.5695C7.8213%2028.8009%207.30685%2028.4272%207.39091%2027.937L8.86925%2019.3176L2.6069%2013.2133C2.25079%2012.8662%202.44729%2012.2614%202.93943%2012.1899L11.5938%2010.9324L15.4641%203.09019Z'%20fill='%231D2529'%20fill-opacity='0.24'/%3e%3c/svg%3e)![](data:image/svg+xml,%3csvg%20width='32'%20height='32'%20viewBox='0%200%2032%2032'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20d='M15.4641%203.09019C15.6842%202.64424%2016.3201%202.64424%2016.5402%203.09019L20.4106%2010.9324L29.0649%2012.1899C29.5571%2012.2614%2029.7536%2012.8662%2029.3975%2013.2133L23.1351%2019.3176L24.6134%2027.937C24.6975%2028.4272%2024.1831%2028.8009%2023.7429%2028.5695L16.0022%2024.5L8.26148%2028.5695C7.8213%2028.8009%207.30685%2028.4272%207.39091%2027.937L8.86925%2019.3176L2.6069%2013.2133C2.25079%2012.8662%202.44729%2012.2614%202.93943%2012.1899L11.5938%2010.9324L15.4641%203.09019Z'%20fill='%231D2529'%20fill-opacity='0.24'/%3e%3c/svg%3e)

### Related Documents

[**API and Code Sample for External Portal Server (Omada Controller 2.5.4 or below)**](https://support.omadanetworks.com/us/document/12916/)

Configuration Guide

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3ccircle%20cx='8'%20cy='8'%20r='5.96154'%20stroke='%232B2B2B'%20stroke-opacity='0.6'%20stroke-width='1.07692'/%3e%3cpath%20d='M8%204V8L10.5%2010'%20stroke='%232B2B2B'%20stroke-opacity='0.6'/%3e%3c/svg%3e)07-06-2023

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20fill-rule='evenodd'%20clip-rule='evenodd'%20d='M8%2013.1924C2.80769%2013.1924%200.5%208.00005%200.5%208.00005C0.5%208.00005%202.80769%202.80774%208%202.80774C13.1923%202.80774%2015.5%208.00005%2015.5%208.00005C15.5%208.00005%2013.1923%2013.1924%208%2013.1924ZM1.79499%207.7102C1.72995%207.81662%201.67332%207.91397%201.62499%208.00005C1.67332%208.08613%201.72995%208.18347%201.79499%208.2899C2.06569%208.73286%202.47566%209.32273%203.0299%209.90958C4.14007%2011.0851%205.76988%2012.1924%208%2012.1924C10.2301%2012.1924%2011.8599%2011.0851%2012.9701%209.90958C13.5243%209.32273%2013.9343%208.73286%2014.205%208.2899C14.27%208.18347%2014.3267%208.08613%2014.375%208.00005C14.3267%207.91397%2014.27%207.81662%2014.205%207.7102C13.9343%207.26723%2013.5243%206.67736%2012.9701%206.09052C11.8599%204.91504%2010.2301%203.80774%208%203.80774C5.76988%203.80774%204.14007%204.91504%203.0299%206.09052C2.47566%206.67736%202.06569%207.26723%201.79499%207.7102ZM9.88462%208.00053C9.88462%209.04137%209.04084%209.88515%208%209.88515C6.95916%209.88515%206.11539%209.04137%206.11539%208.00053C6.11539%206.95969%206.95916%206.11591%208%206.11591C9.04084%206.11591%209.88462%206.95969%209.88462%208.00053ZM10.8846%208.00053C10.8846%209.59366%209.59313%2010.8851%208%2010.8851C6.40687%2010.8851%205.11539%209.59366%205.11539%208.00053C5.11539%206.4074%206.40687%205.11591%208%205.11591C9.59313%205.11591%2010.8846%206.4074%2010.8846%208.00053Z'%20fill='%232B2B2B'%20fill-opacity='0.6'/%3e%3c/svg%3e)8440

[**API and Code Sample for External Portal Server (Omada Controller 2.6.0 to 3.2.17)**](https://support.omadanetworks.com/us/document/12990/)

Configuration Guide

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3ccircle%20cx='8'%20cy='8'%20r='5.96154'%20stroke='%232B2B2B'%20stroke-opacity='0.6'%20stroke-width='1.07692'/%3e%3cpath%20d='M8%204V8L10.5%2010'%20stroke='%232B2B2B'%20stroke-opacity='0.6'/%3e%3c/svg%3e)07-06-2023

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20fill-rule='evenodd'%20clip-rule='evenodd'%20d='M8%2013.1924C2.80769%2013.1924%200.5%208.00005%200.5%208.00005C0.5%208.00005%202.80769%202.80774%208%202.80774C13.1923%202.80774%2015.5%208.00005%2015.5%208.00005C15.5%208.00005%2013.1923%2013.1924%208%2013.1924ZM1.79499%207.7102C1.72995%207.81662%201.67332%207.91397%201.62499%208.00005C1.67332%208.08613%201.72995%208.18347%201.79499%208.2899C2.06569%208.73286%202.47566%209.32273%203.0299%209.90958C4.14007%2011.0851%205.76988%2012.1924%208%2012.1924C10.2301%2012.1924%2011.8599%2011.0851%2012.9701%209.90958C13.5243%209.32273%2013.9343%208.73286%2014.205%208.2899C14.27%208.18347%2014.3267%208.08613%2014.375%208.00005C14.3267%207.91397%2014.27%207.81662%2014.205%207.7102C13.9343%207.26723%2013.5243%206.67736%2012.9701%206.09052C11.8599%204.91504%2010.2301%203.80774%208%203.80774C5.76988%203.80774%204.14007%204.91504%203.0299%206.09052C2.47566%206.67736%202.06569%207.26723%201.79499%207.7102ZM9.88462%208.00053C9.88462%209.04137%209.04084%209.88515%208%209.88515C6.95916%209.88515%206.11539%209.04137%206.11539%208.00053C6.11539%206.95969%206.95916%206.11591%208%206.11591C9.04084%206.11591%209.88462%206.95969%209.88462%208.00053ZM10.8846%208.00053C10.8846%209.59366%209.59313%2010.8851%208%2010.8851C6.40687%2010.8851%205.11539%209.59366%205.11539%208.00053C5.11539%206.4074%206.40687%205.11591%208%205.11591C9.59313%205.11591%2010.8846%206.4074%2010.8846%208.00053Z'%20fill='%232B2B2B'%20fill-opacity='0.6'/%3e%3c/svg%3e)11512

[**API and Code Sample for External Portal Server (Omada Controller 4.1.5 to 4.4.6)**](https://support.omadanetworks.com/us/document/13023/)

Configuration Guide

API

Portal

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3ccircle%20cx='8'%20cy='8'%20r='5.96154'%20stroke='%232B2B2B'%20stroke-opacity='0.6'%20stroke-width='1.07692'/%3e%3cpath%20d='M8%204V8L10.5%2010'%20stroke='%232B2B2B'%20stroke-opacity='0.6'/%3e%3c/svg%3e)07-06-2023

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20fill-rule='evenodd'%20clip-rule='evenodd'%20d='M8%2013.1924C2.80769%2013.1924%200.5%208.00005%200.5%208.00005C0.5%208.00005%202.80769%202.80774%208%202.80774C13.1923%202.80774%2015.5%208.00005%2015.5%208.00005C15.5%208.00005%2013.1923%2013.1924%208%2013.1924ZM1.79499%207.7102C1.72995%207.81662%201.67332%207.91397%201.62499%208.00005C1.67332%208.08613%201.72995%208.18347%201.79499%208.2899C2.06569%208.73286%202.47566%209.32273%203.0299%209.90958C4.14007%2011.0851%205.76988%2012.1924%208%2012.1924C10.2301%2012.1924%2011.8599%2011.0851%2012.9701%209.90958C13.5243%209.32273%2013.9343%208.73286%2014.205%208.2899C14.27%208.18347%2014.3267%208.08613%2014.375%208.00005C14.3267%207.91397%2014.27%207.81662%2014.205%207.7102C13.9343%207.26723%2013.5243%206.67736%2012.9701%206.09052C11.8599%204.91504%2010.2301%203.80774%208%203.80774C5.76988%203.80774%204.14007%204.91504%203.0299%206.09052C2.47566%206.67736%202.06569%207.26723%201.79499%207.7102ZM9.88462%208.00053C9.88462%209.04137%209.04084%209.88515%208%209.88515C6.95916%209.88515%206.11539%209.04137%206.11539%208.00053C6.11539%206.95969%206.95916%206.11591%208%206.11591C9.04084%206.11591%209.88462%206.95969%209.88462%208.00053ZM10.8846%208.00053C10.8846%209.59366%209.59313%2010.8851%208%2010.8851C6.40687%2010.8851%205.11539%209.59366%205.11539%208.00053C5.11539%206.4074%206.40687%205.11591%208%205.11591C9.59313%205.11591%2010.8846%206.4074%2010.8846%208.00053Z'%20fill='%232B2B2B'%20fill-opacity='0.6'/%3e%3c/svg%3e)11603

[**API and Code Sample for RADIUS Server with External Web Portal (Omada Controller 4.1.5 or above)**](https://support.omadanetworks.com/us/document/13025/)

FAQ

Portal

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3ccircle%20cx='8'%20cy='8'%20r='5.96154'%20stroke='%232B2B2B'%20stroke-opacity='0.6'%20stroke-width='1.07692'/%3e%3cpath%20d='M8%204V8L10.5%2010'%20stroke='%232B2B2B'%20stroke-opacity='0.6'/%3e%3c/svg%3e)03-18-2025

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20fill-rule='evenodd'%20clip-rule='evenodd'%20d='M8%2013.1924C2.80769%2013.1924%200.5%208.00005%200.5%208.00005C0.5%208.00005%202.80769%202.80774%208%202.80774C13.1923%202.80774%2015.5%208.00005%2015.5%208.00005C15.5%208.00005%2013.1923%2013.1924%208%2013.1924ZM1.79499%207.7102C1.72995%207.81662%201.67332%207.91397%201.62499%208.00005C1.67332%208.08613%201.72995%208.18347%201.79499%208.2899C2.06569%208.73286%202.47566%209.32273%203.0299%209.90958C4.14007%2011.0851%205.76988%2012.1924%208%2012.1924C10.2301%2012.1924%2011.8599%2011.0851%2012.9701%209.90958C13.5243%209.32273%2013.9343%208.73286%2014.205%208.2899C14.27%208.18347%2014.3267%208.08613%2014.375%208.00005C14.3267%207.91397%2014.27%207.81662%2014.205%207.7102C13.9343%207.26723%2013.5243%206.67736%2012.9701%206.09052C11.8599%204.91504%2010.2301%203.80774%208%203.80774C5.76988%203.80774%204.14007%204.91504%203.0299%206.09052C2.47566%206.67736%202.06569%207.26723%201.79499%207.7102ZM9.88462%208.00053C9.88462%209.04137%209.04084%209.88515%208%209.88515C6.95916%209.88515%206.11539%209.04137%206.11539%208.00053C6.11539%206.95969%206.95916%206.11591%208%206.11591C9.04084%206.11591%209.88462%206.95969%209.88462%208.00053ZM10.8846%208.00053C10.8846%209.59366%209.59313%2010.8851%208%2010.8851C6.40687%2010.8851%205.11539%209.59366%205.11539%208.00053C5.11539%206.4074%206.40687%205.11591%208%205.11591C9.59313%205.11591%2010.8846%206.4074%2010.8846%208.00053Z'%20fill='%232B2B2B'%20fill-opacity='0.6'/%3e%3c/svg%3e)10461

[**API and Code Sample for RADIUS Server with External Web Portal (Omada Controller 3.0.5 or below)**](https://support.omadanetworks.com/us/document/12915/)

FAQ

Portal

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3ccircle%20cx='8'%20cy='8'%20r='5.96154'%20stroke='%232B2B2B'%20stroke-opacity='0.6'%20stroke-width='1.07692'/%3e%3cpath%20d='M8%204V8L10.5%2010'%20stroke='%232B2B2B'%20stroke-opacity='0.6'/%3e%3c/svg%3e)07-06-2023

![](data:image/svg+xml,%3csvg%20width='16'%20height='16'%20viewBox='0%200%2016%2016'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%3e%3cpath%20fill-rule='evenodd'%20clip-rule='evenodd'%20d='M8%2013.1924C2.80769%2013.1924%200.5%208.00005%200.5%208.00005C0.5%208.00005%202.80769%202.80774%208%202.80774C13.1923%202.80774%2015.5%208.00005%2015.5%208.00005C15.5%208.00005%2013.1923%2013.1924%208%2013.1924ZM1.79499%207.7102C1.72995%207.81662%201.67332%207.91397%201.62499%208.00005C1.67332%208.08613%201.72995%208.18347%201.79499%208.2899C2.06569%208.73286%202.47566%209.32273%203.0299%209.90958C4.14007%2011.0851%205.76988%2012.1924%208%2012.1924C10.2301%2012.1924%2011.8599%2011.0851%2012.9701%209.90958C13.5243%209.32273%2013.9343%208.73286%2014.205%208.2899C14.27%208.18347%2014.3267%208.08613%2014.375%208.00005C14.3267%207.91397%2014.27%207.81662%2014.205%207.7102C13.9343%207.26723%2013.5243%206.67736%2012.9701%206.09052C11.8599%204.91504%2010.2301%203.80774%208%203.80774C5.76988%203.80774%204.14007%204.91504%203.0299%206.09052C2.47566%206.67736%202.06569%207.26723%201.79499%207.7102ZM9.88462%208.00053C9.88462%209.04137%209.04084%209.88515%208%209.88515C6.95916%209.88515%206.11539%209.04137%206.11539%208.00053C6.11539%206.95969%206.95916%206.11591%208%206.11591C9.04084%206.11591%209.88462%206.95969%209.88462%208.00053ZM10.8846%208.00053C10.8846%209.59366%209.59313%2010.8851%208%2010.8851C6.40687%2010.8851%205.11539%209.59366%205.11539%208.00053C5.11539%206.4074%206.40687%205.11591%208%205.11591C9.59313%205.11591%2010.8846%206.4074%2010.8846%208.00053Z'%20fill='%232B2B2B'%20fill-opacity='0.6'/%3e%3c/svg%3e)8345

![scroll into top](<Base64-Image-Removed>)

As explained further in our website Privacy Policy, we allow certain advertising partners to collect information from our website through cookies and similar technologies to deliver ads which are more relevant to you, and assist us with advertising-related analytics (e.g., measuring ad performance, optimizing our ad campaigns). This may be considered "selling" or "sharing"/disclosure of personal data for "targeted advertising" as defined by certain U.S. state laws. To opt out of these activities, press "Opt Out" below. If the toggle below for "Targeted Advertising and 'Sale' Cookies" is to the left, you are already opted out and you can close these preferences.

Please note that your choice will apply only to your current device/browser. You must indicate your choice on each device and browser you use to access our website. If you clear your cookies or your browser is set to do so, you must opt out again.

Cookie SettingsAccept All Cookies

Your Privacy Choices

As explained further in our website Privacy Policy, we allow certain advertising partners to collect information from our website through cookies and similar technologies to deliver ads which are more relevant to you, and assist us with advertising-related analytics (e.g., measuring ad performance, optimizing our ad campaigns). This may be considered "selling" or "sharing"/disclosure of personal data for "targeted advertising" as defined by certain U.S. state laws. To opt out of these activities, press "Opt Out" below. If the toggle below for "Targeted Advertising and 'Sale' Cookies" is to the left, you are already opted out and you can close these preferences.

Please note that your choice will apply only to your current device/browser. You must indicate your choice on each device and browser you use to access our website. If you clear your cookies or your browser is set to do so, you must opt out again.

Necessary Cookies

These cookies are necessary for the website to function and cannot be switched off.

TP-Link

SESSION, JSESSIONID, accepted\_local\_switcher, tp\_privacy\_banner, tp\_privacy\_base, tp\_privacy\_marketing, tp\_top-banner, tp\_popup-bottom, tp\_popup-center, tp\_popup-right-middle, tp\_popup-right-bottom, tp\_productCategoryType

Youtube

id, VISITOR\_INFO1\_LIVE, LOGIN\_INFO, SIDCC, SAPISID, APISID, SSID, SID, YSC, \_\_Secure-1PSID, \_\_Secure-1PAPISID, \_\_Secure-1PSIDCC, \_\_Secure-3PSID, \_\_Secure-3PAPISID, \_\_Secure-3PSIDCC, 1P\_JAR, AEC, NID, OTZ

Zendesk

OptanonConsent, \_\_cf\_bm, \_\_cfruid, \_cfuvid, \_help\_center\_session, \_pendo\_\_\_sg\_\_.<container-id>, \_pendo\_meta.<container-id>, \_pendo\_visitorId.<container-id>, \_zendesk\_authenticated, \_zendesk\_cookie, \_zendesk\_session, \_zendesk\_shared\_session, ajs\_anonymous\_id, cf\_clearance

Targeted Advertising and "Sale" Cookies

These cookies allow targeted ads or the "sale" of personal data (toggle to the left to opt out).

Analytics cookies enable us to analyze your activities on our and other websites in order to improve and adapt the functionality of our website and our ad campaigns.

Advertising cookies can be set through our website by our advertising partners in order to create a profile of your interests and to show you relevant advertisements on other websites.

Google Analytics & Google Tag Manager

\_gid, \_ga\_<container-id>, \_ga, \_gat\_gtag\_<container-id>

Google Ads & DoubleClick

test\_cookie, \_gcl\_au

Meta Pixel

\_fbp

Crazy Egg

cebsp\_, \_ce.s, \_ce.clock\_data, \_ce.clock\_event, cebs

Linkedin

lidc, AnalyticsSyncHistory, UserMatchHistory, bcookie, li\_sugr, ln\_or

Reddit

\_rdt\_uuid

Opt OutAccept All CookiesSave Settings

Welcome to Our Website! If you stay on our site, we and our third-party partners use cookies, pixels, and other tracking technologies to better understand how you use our site, provide and improve our services, and personalize your experience and ads based on your interests. Learn more in your privacy choices.

Okay
