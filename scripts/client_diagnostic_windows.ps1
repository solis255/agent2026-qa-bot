#requires -Version 5.1
<#
Windows 10/11. Read this script before running it as an ordinary user.
Writes one JSON file; no configuration changes, elevation, downloads or uploads.
Only fixed DNS queries, default-gateway reachability, and 1.1.1.1:443 are probed.
No MAC, SSID, hostname, account, registry, license or hardware identifiers are exported.
#>
[CmdletBinding()]
param([string]$OutputPath = (Join-Path (Get-Location) 'netpilot-client-diagnostic.json'))

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
$InformationPreference = 'SilentlyContinue'

function Has-Command([string]$Name) {
    return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Read-OnlyValue([scriptblock]$Action, [string]$Component) {
    try {
        $value = & $Action
        if ($Component -and $script:collectionStatus[$Component] -ne 'error') { $script:collectionStatus[$Component] = 'normal' }
        return $value
    } catch {
        if ($Component) { $script:collectionStatus[$Component] = 'error' }
        return $null
    }
}

function Get-Probe([string]$Id, [string]$Kind, [string]$Target) {
    $result = @{}
    if ($Kind -eq 'tcp_connectivity') { $result.port = 443 }
    $status = 'unsupported'
    $elapsed = $null
    $commandName = if ($Kind -eq 'dns') { 'Resolve-DnsName' } else { 'Test-NetConnection' }
    if (-not (Has-Command $commandName)) {
        $result.error_code = 'cmdlet_unavailable'
    } elseif ($Target -eq 'unknown') {
        $status = 'error'
        $result.error_code = 'gateway_unknown'
    } else {
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            if ($Kind -eq 'dns') {
                $answers = @(Resolve-DnsName -Name $Target -DnsOnly -NoHostsFile -QuickTimeout -ErrorAction Stop |
                    Where-Object { $_.Type -eq 'A' -or $_.Type -eq 'AAAA' } |
                    Select-Object -ExpandProperty IPAddress -Unique | Select-Object -First 16)
                $result.addresses = @($answers)
                $status = if ($answers.Count -gt 0) { 'normal' } else { 'abnormal' }
                if ($status -eq 'abnormal') { $result.error_code = 'dns_query_failed' }
            } else {
                $ok = if ($Kind -eq 'tcp_connectivity') {
                    Test-NetConnection -ComputerName $Target -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
                } else {
                    Test-NetConnection -ComputerName $Target -InformationLevel Quiet -WarningAction SilentlyContinue
                }
                $result.reachable = [bool]$ok
                $status = if ($ok) { 'normal' } else { 'abnormal' }
                if (-not $ok) { $result.error_code = 'probe_failed' }
            }
        } catch {
            # Do not serialize ErrorRecord, localized messages or exception strings.
            if ($Kind -eq 'dns' -and $_.FullyQualifiedErrorId -match 'DNS_ERROR|DNS_INFO|DNS_STATUS') {
                $status = 'abnormal'
                $result.error_code = 'dns_query_failed'
            } else {
                $status = 'error'
                $result.error_code = 'collection_error'
            }
        } finally {
            $timer.Stop()
            $elapsed = [math]::Round($timer.Elapsed.TotalMilliseconds, 2)
        }
    }
    return @{ check_id = $Id; type = $Kind; target = $Target; status = $status; latency_ms = $elapsed; result = $result }
}

try {
    $capturedAt = [DateTime]::UtcNow.ToString('o')
    $script:collectionStatus = @{ os='unsupported'; adapters='unsupported'; ip_configuration='unsupported'; dns_servers='unsupported'; routes='unsupported'; connection_profile='unsupported'; proxy='unsupported' }
    $commandMap = @{ os='Get-CimInstance'; adapters='Get-NetAdapter'; ip_configuration='Get-NetIPConfiguration'; dns_servers='Get-DnsClientServerAddress'; routes='Get-NetRoute'; connection_profile='Get-NetConnectionProfile'; proxy='netsh.exe' }
    foreach ($component in $commandMap.Keys) {
        if (Has-Command $commandMap[$component]) { $script:collectionStatus[$component] = 'unknown' }
    }
    $osInfo = if (Has-Command 'Get-CimInstance') { Read-OnlyValue { Get-CimInstance -ClassName Win32_OperatingSystem } 'os' } else { $null }
    $version = if ($osInfo) { [string]$osInfo.Version } else { $null }
    $build = if ($osInfo) { [string]$osInfo.BuildNumber } else { $null }
    $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { 'arm64' } elseif ([Environment]::Is64BitOperatingSystem) { 'x64' } else { 'x86' }
    $netAdapters = if (Has-Command 'Get-NetAdapter') { @(Read-OnlyValue { Get-NetAdapter | Select-Object -First 32 } 'adapters') } else { @() }
    $netAdapters = @($netAdapters | Where-Object { $null -ne $_ })
    $ipConfigs = if (Has-Command 'Get-NetIPConfiguration') { @(Read-OnlyValue { Get-NetIPConfiguration } 'ip_configuration') } else { @() }
    $routes = @()
    if (Has-Command 'Get-NetRoute') {
        $routes += @(Read-OnlyValue { Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' } 'routes')
        $routes += @(Read-OnlyValue { Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0' } 'routes')
    }
    $routes = @($routes | Where-Object { $null -ne $_ } | Select-Object -First 16)
    $adapterMap = @{}
    $adapters = @()
    $counter = 0
    foreach ($adapter in $netAdapters) {
        $counter++
        $id = 'if-' + $counter
        $adapterMap[[int]$adapter.ifIndex] = $id
        $config = $ipConfigs | Where-Object { $_.InterfaceIndex -eq $adapter.ifIndex } | Select-Object -First 1
        $type = if ($adapter.InterfaceType -eq 71) { 'wifi' } elseif ($adapter.InterfaceType -eq 24) { 'loopback' } elseif (-not $adapter.HardwareInterface) { 'virtual' } elseif ($adapter.InterfaceType -eq 6) { 'ethernet' } else { 'other' }
        $status = if ($adapter.Status -eq 'Up') { 'up' } elseif ($adapter.Status -in @('Disconnected', 'Disabled', 'Not Present', 'Down')) { 'down' } else { 'unknown' }
        $ipv4 = if ($config) { @($config.IPv4Address | Where-Object { $_ } | Select-Object -ExpandProperty IPAddress -First 16) } else { @() }
        $ipv6 = if ($config) { @($config.IPv6Address | Where-Object { $_ } | Select-Object -ExpandProperty IPAddress -First 16) } else { @() }
        $hasGateway = if (Has-Command 'Get-NetRoute') { [bool]@($routes | Where-Object { $_.InterfaceIndex -eq $adapter.ifIndex }).Count } else { $null }
        $adapters += @{ adapter_id=$id; name=$id; interface_alias=$null; status=$status; interface_type=$type; ipv4_addresses=@($ipv4); ipv6_addresses=@($ipv6); has_default_gateway=$hasGateway }
    }
    # Select using IPv4 default-route plus interface metric, never the first Up NIC.
    $rankedRoutes = @($routes | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' -and $adapterMap.ContainsKey([int]$_.InterfaceIndex) } | Sort-Object @{Expression={
        $route = $_
        $config = $ipConfigs | Where-Object { $_.InterfaceIndex -eq $route.InterfaceIndex } | Select-Object -First 1
        [long]$route.RouteMetric + [long]$config.IPv4Interface.InterfaceMetric
    }})
    $activeId = $null
    $gateway = $null
    $activeIndex = $null
    if ($rankedRoutes.Count -gt 0) {
        # Equal-cost different interfaces cannot be reliably attributed to one NIC.
        $first = $rankedRoutes[0]
        $equal = @($rankedRoutes | Where-Object { $_.RouteMetric -eq $first.RouteMetric -and $_.InterfaceIndex -ne $first.InterfaceIndex })
        if ($equal.Count -eq 0) {
            $activeIndex = [int]$first.InterfaceIndex
            $activeId = $adapterMap[$activeIndex]
            if ($first.NextHop -and $first.NextHop -ne '0.0.0.0') { $gateway = [string]$first.NextHop }
        }
    }
    $dns = @()
    $dnsScope = 'unknown'
    if (Has-Command 'Get-DnsClientServerAddress') {
        $indices = if ($null -ne $activeIndex) { @($activeIndex) } else { @($netAdapters | Where-Object { $_.Status -eq 'Up' } | Select-Object -ExpandProperty ifIndex) }
        foreach ($index in $indices) {
            $values = @(Read-OnlyValue { Get-DnsClientServerAddress -InterfaceIndex $index } 'dns_servers')
            foreach ($entry in $values) { if ($entry) { $dns += @($entry.ServerAddresses) } }
        }
        $dns = @($dns | Where-Object { $_ } | Select-Object -Unique -First 16)
        if ($indices.Count -gt 0) { $dnsScope = if ($null -ne $activeIndex) { 'active_adapter' } else { 'up_adapters' } }
    }
    $profile = $null
    if ($null -ne $activeIndex -and (Has-Command 'Get-NetConnectionProfile')) {
        $rawProfile = Read-OnlyValue { Get-NetConnectionProfile -InterfaceIndex $activeIndex | Select-Object -First 1 } 'connection_profile'
        if ($rawProfile) {
            $category = switch ([string]$rawProfile.NetworkCategory) { 'Public' { 'public' } 'Private' { 'private' } 'DomainAuthenticated' { 'domain' } default { 'unknown' } }
            $profile = @{ network_category=$category; ipv4_connectivity=[string]$rawProfile.IPv4Connectivity; ipv6_connectivity=[string]$rawProfile.IPv6Connectivity }
        }
    }
    $proxy = @{ winhttp_proxy_enabled=$null; winhttp_proxy=$null }
    if (Has-Command 'netsh.exe') {
        $proxyText = (Read-OnlyValue { netsh.exe winhttp show proxy 2>$null } 'proxy') -join ' '
        if ($proxyText -match 'Direct access|直接访问') {
            $proxy.winhttp_proxy_enabled = $false
        } elseif ($proxyText -match '(?:https?=)?(?:[a-zA-Z0-9.-]+|\[[0-9a-fA-F:]+\]):\d{1,5}') {
            $endpoint = $Matches[0]
            # Keep a single endpoint only; never pass through proxy/bypass credentials.
            if ($proxyText -notmatch '@') {
                $proxy.winhttp_proxy_enabled = $true
                $proxy.winhttp_proxy = $endpoint
            }
        }
    }
    $routeSummary = @()
    foreach ($route in $routes) {
        $routeSummary += @{ destination=[string]$route.DestinationPrefix; next_hop=[string]$route.NextHop; interface_id=$adapterMap[[int]$route.InterfaceIndex]; metric=[int]$route.RouteMetric }
    }
    $checks = @(
        (Get-Probe 'dns-tju' 'dns' 'www.tju.edu.cn'),
        (Get-Probe 'dns-baidu' 'dns' 'www.baidu.com'),
        (Get-Probe 'gateway' 'gateway_reachability' $(if ($gateway) { $gateway } else { 'unknown' })),
        (Get-Probe 'tcp-443' 'tcp_connectivity' '1.1.1.1')
    )
    $snapshot = @{
        schema_version=1; generated_at=$capturedAt
        collection_status=$script:collectionStatus
        client=@{ client_instance_id=[Guid]::NewGuid().ToString(); hostname=$null }
        os=@{ family='windows'; version=$version; build=$build; architecture=$architecture }
        adapters=@($adapters); active_adapter_id=$activeId; default_gateway=$gateway
        dns_servers=@($dns); dns_servers_scope=$dnsScope; connection_profile=$profile
        proxy=$proxy; route_summary=@($routeSummary); checks=@($checks)
        redaction=@{ hostname_redacted=$true; mac_removed=$true; ssid_removed=$true; secrets_removed=$true }
    }
    $json = $snapshot | ConvertTo-Json -Depth 10
    # Fail locally rather than generate an unreadable/truncated JSON file.
    $null = $json | ConvertFrom-Json
    $resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
    [IO.File]::WriteAllText($resolvedOutput, $json, (New-Object Text.UTF8Encoding($false)))
    Write-Output ('Snapshot saved to ' + $resolvedOutput)
} catch {
    # No raw exception or system values on stdout/stderr.
    Write-Error 'Snapshot could not be generated or written.' -ErrorAction Continue
    exit 1
}
