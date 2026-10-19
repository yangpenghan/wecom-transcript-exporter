param([int]$ProcessId, [string]$Database, [int]$Seconds=40, [long]$StartAddress=0, [string]$OutputDirectory)
$ErrorActionPreference='Stop'
if (-not $OutputDirectory) { throw 'An output directory is required' }
$OutputDirectory=(Resolve-Path -LiteralPath $OutputDirectory).Path
$cs = @'

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

public class ScopedVoiceRoomKeyScan {
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint a, bool inh, int pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", SetLastError=true)] static extern long VirtualQueryEx(IntPtr h, IntPtr addr, out MBI mbi, uint len);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr read);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr h, uint acc, out IntPtr tok);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool LookupPrivilegeValue(string s, string n, out long luid);
    [DllImport("advapi32.dll", SetLastError=true)] static extern bool AdjustTokenPrivileges(IntPtr tok, bool dis, ref TP newp, uint len, IntPtr prev, IntPtr ret);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();

    [StructLayout(LayoutKind.Sequential)] struct MBI {
        public IntPtr BaseAddress, AllocationBase;
        public uint AllocationProtect, __a1;
        public IntPtr RegionSize;
        public uint State, Protect, Type, __a2;
    }
    [StructLayout(LayoutKind.Sequential)] struct TP { public uint Count; public long Luid; public uint Attr; }

    const uint MEM_COMMIT=0x1000, MEM_PRIVATE=0x20000;
    const uint PAGE_RW=0x04, PAGE_WC=0x08, PAGE_GUARD=0x100, PAGE_NOACCESS=0x01;


    public static long NextAddress, Candidates;
    public static bool TimedOut;
    public static int Seconds = 40;
    public static long StartAddress;
    static System.Diagnostics.Stopwatch timer;
    static byte[] FRAG, CIPHER, IV, SUF;
    static MD5 md5 = MD5.Create();
    static Aes AES;

    static int PC(ulong x){ int c=0; while(x!=0){ x&=x-1; c++; } return c; }

    static bool Hit(byte[] b, int o) {
        ulong m0=0,m1=0,m2=0,m3=0; int na=0;
        for (int j=0;j<16;j++){
            byte v=b[o+j];
            int w=v>>6; ulong bit=1UL<<(v&63);
            if(w==0)m0|=bit; else if(w==1)m1|=bit; else if(w==2)m2|=bit; else m3|=bit;
            if(v<0x20||v>0x7e) na++;
        }
        if (na<3) return false;
        if (PC(m0)+PC(m1)+PC(m2)+PC(m3) < 11) return false;
        byte[] inp=new byte[24];
        Array.Copy(b,o,inp,0,16); Array.Copy(SUF,0,inp,16,8);
        byte[] pk=md5.ComputeHash(inp);
        AES.Key=pk;
        using (var d=AES.CreateDecryptor()){
            byte[] pt=d.TransformFinalBlock(CIPHER,0,16);
            for(int j=0;j<8;j++) if((pt[j]^IV[j])!=FRAG[j]) return false;
            return true;
        }
    }

    public static List<string> Run(int pid, byte[] frag, byte[] cipher, byte[] iv, out long mb) {
        timer=System.Diagnostics.Stopwatch.StartNew(); FRAG=frag; CIPHER=cipher; IV=iv;
        SUF=new byte[]{1,0,0,0,0x73,0x41,0x6c,0x54};
        AES=Aes.Create(); AES.Mode=CipherMode.ECB; AES.Padding=PaddingMode.None;
        var found=new List<string>(); mb=0;
        IntPtr h=OpenProcess(0x0010|0x0400, false, pid);   // VM_READ | QUERY_INFORMATION
        if (h==IntPtr.Zero) throw new Exception("OpenProcess "+pid+" failed err="+Marshal.GetLastWin32Error());
        IntPtr addr=(IntPtr)StartAddress; MBI mbi; uint sz=(uint)Marshal.SizeOf(typeof(MBI));
        long scanned=0;
        while (VirtualQueryEx(h, addr, out mbi, sz)!=0) {
            if (timer.Elapsed.TotalSeconds >= Seconds) { TimedOut=true; NextAddress=addr.ToInt64(); CloseHandle(h); mb=scanned/1048576; return found; }
            ulong baseA=(ulong)mbi.BaseAddress.ToInt64();
            ulong size=(ulong)mbi.RegionSize.ToInt64();
            bool ok = mbi.State==MEM_COMMIT && mbi.Type==MEM_PRIVATE
                      && (mbi.Protect==PAGE_RW || mbi.Protect==PAGE_WC)
                      && (mbi.Protect & (PAGE_GUARD|PAGE_NOACCESS))==0;
            if (ok && size>0 && size<0x40000000UL) {
                try {
                    byte[] buf=new byte[size]; IntPtr rd;
                    if (ReadProcessMemory(h, mbi.BaseAddress, buf, (IntPtr)size, out rd)) {
                        int n=(int)rd; scanned+=n;
                        for (int o=(int)Math.Max(0,StartAddress-(long)baseA); o+16<=n; o+=8) {
                            if ((o & 65535)==0 && timer.Elapsed.TotalSeconds >= Seconds) {
                                TimedOut=true; NextAddress=(long)baseA+o; CloseHandle(h); mb=scanned/1048576; return found;
                            }
                            Candidates++;
                            if (Hit(buf,o)) {
                                var sb=new System.Text.StringBuilder();
                                for(int j=0;j<16;j++) sb.Append(buf[o+j].ToString("x2"));
                                string hex=sb.ToString();
                                if(!found.Contains(hex)) found.Add(hex);
                                if(found.Count>=1){ CloseHandle(h); mb=scanned/1048576; return found; }
                            }
                        }
                    }
                } catch {}
            }
            ulong next=baseA+size; if(next<=baseA) break;
            addr=(IntPtr)(long)next; if(next>0x7FFFFFFFFFFFUL) break;
        }
        CloseHandle(h); mb=scanned/1048576; return found;
    }
}

'@
Add-Type -TypeDefinition $cs -Language CSharp
Add-Type -AssemblyName System.Security
$target = Get-Process -Id $ProcessId -ErrorAction Stop
if ($target.ProcessName -ne 'WXWork') { throw 'Expected WXWork process' }
$currentSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$currentSession=(Get-Process -Id $PID).SessionId
$targetInfo=Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId"
$owner=Invoke-CimMethod -InputObject $targetInfo -MethodName GetOwnerSid
if ($owner.ReturnValue -ne 0 -or $owner.Sid -ne $currentSid -or $targetInfo.SessionId -ne $currentSession) {
    throw 'Expected WeCom owned by the current Windows user in the current session'
}
$db = (Resolve-Path -LiteralPath $Database).Path
if ([IO.Path]::GetFileName($db) -ne 'voice_room5.db') { throw 'Expected voice_room5.db' }
$header=New-Object byte[] 4096
$stream=[IO.File]::Open($db,'Open','Read','ReadWrite')
try { if ($stream.Read($header,0,4096) -ne 4096) { throw 'Incomplete page' } } finally { $stream.Close() }
if ([BitConverter]::ToString($header[16..23]) -ne '10-00-02-02-00-40-20-20') { throw 'Unsupported header' }
$iv=[byte[]](0x20,0xd7,0x42,0x0f,0x9c,0x37,0xa3,0x5d,0xca,0x6f,0xe9,0x2a,0x1c,0x69,0x99,0xa9)
[ScopedVoiceRoomKeyScan]::Seconds=$Seconds
[ScopedVoiceRoomKeyScan]::StartAddress=$StartAddress
$scannedMB=0
$timer=[Diagnostics.Stopwatch]::StartNew()
$found=[ScopedVoiceRoomKeyScan]::Run($ProcessId,$header[16..23],($header[8..15]+$header[24..31]),$iv,[ref]$scannedMB)
$ok=$found.Count -gt 0
if ($ok) {
    $hex=$found[0]
    $key=New-Object byte[] 16
    for($i=0;$i -lt 16;$i++){ $key[$i]=[Convert]::ToByte($hex.Substring($i*2,2),16) }
    $protected=[Security.Cryptography.ProtectedData]::Protect($key,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    [IO.File]::WriteAllBytes((Join-Path $OutputDirectory 'voice-room-key.dpapi'),$protected)
    [Array]::Clear($key,0,$key.Length)
}
$report=@{ found=$ok; timed_out=[ScopedVoiceRoomKeyScan]::TimedOut; next_address=[ScopedVoiceRoomKeyScan]::NextAddress; candidates=[ScopedVoiceRoomKeyScan]::Candidates; megabytes_read=$scannedMB; seconds=[math]::Round($timer.Elapsed.TotalSeconds,2) }
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory 'scoped-key-probe.json') -Encoding UTF8
$report | ConvertTo-Json
