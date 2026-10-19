<?php
// Included by badges.php. No credentials or arbitrary user IDs in returned diagnostics.
declare(strict_types=1);
if (realpath($_SERVER['SCRIPT_FILENAME'] ?? '') === __FILE__) { http_response_code(404); exit; }
function qmodsVkRequest(string $endpoint, string $token, string $userAgent): array {
    $body = '';
    $ch = curl_init($endpoint);
    curl_setopt_array($ch, [CURLOPT_POST=>true,
        CURLOPT_POSTFIELDS=>http_build_query(['access_token'=>$token,'v'=>'5.289','fields'=>'photo_100,photo_200,status,online,counters']),
        CURLOPT_USERAGENT=>$userAgent, CURLOPT_CONNECTTIMEOUT=>3, CURLOPT_TIMEOUT=>8,
        CURLOPT_FOLLOWLOCATION=>false, CURLOPT_SSL_VERIFYPEER=>true, CURLOPT_SSL_VERIFYHOST=>2,
        CURLOPT_HTTPHEADER=>['Origin: https://m.vk.ru','Referer: https://m.vk.ru/','Accept: application/json'],
        CURLOPT_WRITEFUNCTION=>static function($ch,string $chunk) use(&$body): int {
            if (strlen($body)+strlen($chunk)>65536) return 0;
            $body.=$chunk; return strlen($chunk);
        }]);
    $ok=curl_exec($ch); $status=(int)curl_getinfo($ch,CURLINFO_HTTP_CODE); unset($ch);
    $json=json_decode($body,true);
    return ['http'=>$status,'json'=>is_array($json)?$json:null,'transport_ok'=>$ok!==false];
}
function qmodsVerifyVk(string $token, string $userAgent, ?callable $transport=null): array {
    $transport ??= 'qmodsVkRequest';
    $attempts=[]; $lastCode=0; $hadVkError=false;
    // Fixed official endpoints only; the caller cannot supply a URL or user_ids.
    foreach (['api'=>'https://api.vk.ru/method/users.get','web_api'=>'https://web.api.vk.ru/method/users.get'] as $name=>$url) {
        $result=$transport($url,$token,$userAgent); $json=$result['json'] ?? null;
        $code=is_array($json) && is_array($json['error'] ?? null) ? (int)($json['error']['error_code'] ?? 0) : 0;
        $attempts[]=['endpoint'=>$name,'http'=>(int)($result['http'] ?? 0),'vk_code'=>$code];
        if (!($result['transport_ok'] ?? false) || !is_array($json)) continue;
        if (isset($json['error'])) {
            $hadVkError=true; $lastCode=$code;
            // Do not retry a VK rate limit, captcha or account-validation challenge.
            if (in_array($code,[6,9,14,17,24],true)) break;
            continue;
        }
        $users=$json['response'] ?? null;
        $id=is_array($users) && count($users)===1 && is_array($users[0] ?? null) ? ($users[0]['id'] ?? 0) : 0;
        if ((int)($result['http'] ?? 0)===200 && is_int($id) && $id>0) {
            return ['id'=>$id,'vk_code'=>0,'attempts'=>$attempts];
        }
    }
    return ['id'=>0,'error'=>$hadVkError?'vk_auth_failed':'vk_unavailable','vk_code'=>$lastCode,'attempts'=>$attempts];
}
