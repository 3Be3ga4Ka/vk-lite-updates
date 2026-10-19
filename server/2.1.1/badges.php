<?php
// PHP 8.1+, curl. Compatible with VK Lite schema 2. No tokens or cookies stored.
declare(strict_types=1);
// API output must stay JSON even when hosting enables display_errors (PHP 8.5).
ini_set('display_errors', '0');
ini_set('display_startup_errors', '0');
ob_start();

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
function reply(int $status, array $data): never {
    if (ob_get_level() > 0) ob_clean();
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    exit;
}
const GUARD = "<?php\nhttp_response_code(404);\nexit;\n__halt_compiler();\n";
const MAX_STATE = 16777216;
function stateRead(string $file): array {
    if (!is_file($file)) return ['secret'=>base64_encode(random_bytes(32)), 'badges'=>[], 'limits'=>[]];
    $size = filesize($file);
    if ($size === false || $size > MAX_STATE || $size < strlen(GUARD)) throw new RuntimeException('state');
    $raw = file_get_contents($file);
    if (!is_string($raw) || !str_starts_with($raw, GUARD)) throw new RuntimeException('guard');
    $state = json_decode(substr($raw, strlen(GUARD)), true, 128, JSON_THROW_ON_ERROR);
    if (!is_array($state) || !is_array($state['badges'] ?? null) || !is_array($state['limits'] ?? null)
        || !is_string($state['secret'] ?? null) || strlen((string)base64_decode($state['secret'], true)) !== 32) {
        throw new RuntimeException('state');
    }
    return $state;
}
function stateWrite(string $file, array $state): void {
    $raw = GUARD . json_encode($state, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    if (strlen($raw) > MAX_STATE) throw new RuntimeException('capacity');
    // Temp files also end in .php and begin with the same executable 404 guard.
    $temp = dirname($file).'/state-'.bin2hex(random_bytes(8)).'.tmp.php';
    $handle = fopen($temp, 'x+b');
    if ($handle === false) throw new RuntimeException('storage');
    try {
        chmod($temp, 0600);
        $offset = 0;
        while ($offset < strlen($raw)) {
            $n = fwrite($handle, substr($raw, $offset));
            if ($n === false || $n === 0) throw new RuntimeException('storage');
            $offset += $n;
        }
        if (!fflush($handle)) throw new RuntimeException('storage');
        if (function_exists('fsync') && !fsync($handle)) throw new RuntimeException('storage');
        fclose($handle); $handle = null;
        if (!rename($temp, $file)) throw new RuntimeException('storage');
    } finally {
        if (is_resource($handle)) fclose($handle);
        if (is_file($temp)) unlink($temp);
    }
}
/** A separate guarded lock file serializes read/modify/atomic-rename operations. */
function stateChange(string $storage, callable $operation): mixed {
    $lock = fopen($storage.'/lock.php', 'c+b');
    if ($lock === false) throw new RuntimeException('lock');
    try {
        if (!flock($lock, LOCK_EX)) throw new RuntimeException('lock');
        if (fstat($lock)['size'] === 0) {
            if (fwrite($lock, GUARD) !== strlen(GUARD) || !fflush($lock)) throw new RuntimeException('lock');
            chmod($storage.'/lock.php', 0600);
        }
        $file = $storage.'/state.php';
        $state = stateRead($file);
        $result = $operation($state);
        stateWrite($file, $state);
        return $result;
    } finally { flock($lock, LOCK_UN); fclose($lock); }
}
if (!in_array($_SERVER['HTTPS'] ?? '', ['on','1'], true)) reply(400, ['error'=>'https_required']);
$method = $_SERVER['REQUEST_METHOD'] ?? '';
if (!in_array($method, ['GET','POST'], true)) reply(405, ['error'=>'method']);
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 12000) reply(413, ['error'=>'body_too_large']);
if (!function_exists('curl_init')) reply(503, ['error'=>'curl_required']);
try {
    $config = is_file(__DIR__.'/config.php') ? (require __DIR__.'/config.php') : [];
    $storage = is_array($config) ? ($config['storage'] ?? __DIR__.'/_data') : __DIR__.'/_data';
    if (!is_string($storage) || $storage === '') reply(503, ['error'=>'setup_required']);
    if (!is_dir($storage) && !mkdir($storage, 0700, true) && !is_dir($storage)) reply(503, ['error'=>'setup_required']);
    $storage = realpath($storage);
    if ($storage === false || !is_writable($storage)) reply(503, ['error'=>'setup_required']);
    // Works with PHP on nginx as well; Apache additionally denies the directory.
    foreach (['index.php'=>GUARD, '.htaccess'=>"Require all denied\n"] as $name=>$text) {
        if (!is_file($storage.'/'.$name) && file_put_contents($storage.'/'.$name, $text, LOCK_EX) === false) {
            reply(503, ['error'=>'setup_required']);
        }
    }
    $allowed = stateChange($storage, function(array &$state): bool {
        $bucket = intdiv(time(), 60);
        $key = hash_hmac('sha256', $_SERVER['REMOTE_ADDR'] ?? 'unknown', $state['secret']);
        foreach ($state['limits'] as $hash=>$limit) if (($limit['window'] ?? 0) < $bucket-60) unset($state['limits'][$hash]);
        if (!isset($state['limits'][$key]) && count($state['limits']) >= 5000) return false;
        $old = $state['limits'][$key] ?? [];
        $n = ($old['window'] ?? -1) === $bucket ? (int)$old['count']+1 : 1;
        $state['limits'][$key] = ['window'=>$bucket, 'count'=>min($n, 121)];
        return $n <= 120;
    });
    if (!$allowed) { header('Retry-After: 60'); reply(429, ['error'=>'rate_limit']); }
    $action = $method === 'GET' ? ($_GET['action'] ?? 'lookup') : ($_POST['action'] ?? '');
    if ($method === 'GET' && $action === 'health') reply(200, ['schema'=>2, 'ready'=>true, 'storage'=>'guarded_php', 'server_version'=>'2.1.1']);
    if ($method === 'GET' && $action === 'lookup') {
        $raw = $_GET['ids'] ?? '';
        if (!is_string($raw) || strlen($raw) > 1600) reply(400, ['error'=>'ids']);
        $parts = $raw === '' ? [] : explode(',', $raw);
        foreach ($parts as $id) if (!preg_match('/^[1-9][0-9]{0,12}$/D', $id)) reply(400, ['error'=>'ids']);
        $ids = array_values(array_unique($parts));
        if (count($ids) > 100) reply(400, ['error'=>'too_many_ids']);
        $users = stateChange($storage, function(array &$state) use($ids): array {
            $users=[];
            foreach ($ids as $id) if (isset($state['badges'][$id])) {
                $badge=$state['badges'][$id];
                $users[]=['id'=>(int)$id, 'style'=>$badge['style'], 'updated'=>$badge['updated']];
            }
            return $users;
        });
        reply(200, ['schema'=>2, 'users'=>$users]);
    }
    if ($method !== 'POST' || !in_array($action, ['enroll','remove'], true)) reply(400, ['error'=>'action']);
    $token = $_POST['access_token'] ?? '';
    if (!is_string($token) || strlen($token)<12 || strlen($token)>8192) reply(401, ['error'=>'vk_auth_required']);
    $style = $_POST['style'] ?? 'qmods';
    if ($action==='enroll' && !in_array($style, ['qmods','blue','violet','green','amber'], true)) reply(400, ['error'=>'style']);
    // No user_ids: VK returns the actual token owner. No token is written to disk.
    $response = '';
    $ch = curl_init('https://api.vk.ru/method/users.get');
    curl_setopt_array($ch, [CURLOPT_POST=>true, CURLOPT_POSTFIELDS=>http_build_query(['access_token'=>$token,'v'=>'5.289']),
        CURLOPT_CONNECTTIMEOUT=>5, CURLOPT_TIMEOUT=>12, CURLOPT_FOLLOWLOCATION=>false,
        CURLOPT_SSL_VERIFYPEER=>true, CURLOPT_SSL_VERIFYHOST=>2,
        CURLOPT_HTTPHEADER=>['Origin: https://m.vk.ru','Referer: https://m.vk.ru/'],
        CURLOPT_WRITEFUNCTION=>static function($ch, string $chunk) use (&$response): int {
            if (strlen($response)+strlen($chunk)>65536) return 0;
            $response.=$chunk; return strlen($chunk);
        }]);
    unset($token, $_POST['access_token']);
    $ok=curl_exec($ch); $code=curl_getinfo($ch,CURLINFO_HTTP_CODE); unset($ch);
    if ($ok===false || $code!==200) reply(502, ['error'=>'vk_unavailable']);
    $json=json_decode($response,true); $id=$json['response'][0]['id'] ?? 0;
    if (!is_int($id) || $id<=0) reply(401, ['error'=>'vk_auth_failed']);
    stateChange($storage, function(array &$state) use($id,$style,$action): void {
        if ($action==='remove') unset($state['badges'][(string)$id]);
        else {
            if (!isset($state['badges'][(string)$id]) && count($state['badges'])>=100000) throw new RuntimeException('capacity');
            $state['badges'][(string)$id]=['style'=>$style, 'updated'=>time()];
        }
    });
    if ($action==='remove') reply(200, ['schema'=>2,'id'=>$id,'enabled'=>false]);
    reply(200, ['schema'=>2,'id'=>$id,'style'=>$style,'enabled'=>true]);
} catch (Throwable $e) { reply(503, ['error'=>'service_unavailable']); }
