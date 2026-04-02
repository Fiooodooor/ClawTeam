# Kerberos Authentication Setup (Dev Container)

This guide explains how to set up Kerberos authentication inside the
development container to access Intel internal services such as HSDES.

---

## 1. Prerequisites

- Intel corporate network access (VPN or direct)
- Your Intel IDSID
- The dev container must have Intel DNS servers configured in
  `/etc/resolv.conf`

---

## 2. Install Kerberos Client Tools

```bash
sudo apt install krb5-user
```

> If prompted for a default realm during installation, enter
> `GER.CORP.INTEL.COM` (for Israel-based employees). See
> [Section 4](#4-realm-selection) for other regions.

---

## 3. Configure `/etc/krb5.conf`

Replace the contents of `/etc/krb5.conf` with the following:

```ini
[libdefaults]
    default_realm = GER.CORP.INTEL.COM
    dns_lookup_realm = true
    dns_lookup_kdc = true
    kdc_timesync = 1
    ccache_type = 4
    forwardable = true
    proxiable = true

[realms]
    GER.CORP.INTEL.COM = {
        kdc = hasger603.ger.corp.intel.com
        kdc = hasger501.ger.corp.intel.com
        kdc = scsger702.ger.corp.intel.com
        kdc = fmsger602.ger.corp.intel.com
        admin_server = hasger603.ger.corp.intel.com
        default_domain = ger.corp.intel.com
    }

[domain_realm]
    .intel.com = GER.CORP.INTEL.COM
    intel.com = GER.CORP.INTEL.COM
    .ger.corp.intel.com = GER.CORP.INTEL.COM
    ger.corp.intel.com = GER.CORP.INTEL.COM
```

> Adjust the realm and KDC servers for your region. See
> [Section 4](#4-realm-selection).

---

## 4. Realm Selection

Intel uses regional Kerberos realms under `CORP.INTEL.COM`. Use the one
matching your site:

| Region             | Realm                  |
|--------------------|------------------------|
| Israel / Europe    | `GER.CORP.INTEL.COM`   |
| Americas           | `AMR.CORP.INTEL.COM`   |
| Global (fallback)  | `CORP.INTEL.COM`       |

To discover KDC servers for your realm, run:

```bash
host -t SRV _kerberos._tcp.<realm>
```

For example:

```bash
host -t SRV _kerberos._tcp.ger.corp.intel.com
```

---

## 5. Obtain a Kerberos Ticket

```bash
kinit <your-idsid>@GER.CORP.INTEL.COM
```

Enter your Intel password when prompted.

---

## 6. Verify the Ticket

```bash
klist
```

You should see a valid ticket-granting ticket (TGT) with an expiration
time (typically 10 hours).

---

## 7. Access Intel Services

### HSDES (browser-style access via curl)

```bash
curl --negotiate -u : -s -L \
  "https://hsdes-api.intel.com/rest/article/<article-id>"
```

### General negotiate-auth

Any service supporting SPNEGO/Kerberos:

```bash
curl --negotiate -u : -s -L "<url>"
```

---

## 8. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Cannot find KDC for realm` | Missing or wrong realm in `krb5.conf` | Update `krb5.conf` with correct realm and KDC servers |
| `Client not found in Kerberos database` | Wrong IDSID or wrong realm | Verify IDSID; try a different regional realm |
| `Preauthentication failed` | Wrong password | Re-enter password carefully |
| DNS lookup failures | Container not on Intel network | Check `/etc/resolv.conf` for Intel DNS servers |

---

## 9. Ticket Renewal

Tickets expire after ~10 hours. To renew:

```bash
kinit -R
```

If renewal fails, obtain a new ticket with `kinit`.

---

## 10. Notes for Dev Containers

- The `/etc/krb5.conf` file is reset when the container is rebuilt.
  Consider adding the configuration to your container setup scripts.
- If the host already has a Kerberos ticket, you can mount the credential
  cache into the container by mapping `/tmp/krb5cc_$(id -u)`.
- Ensure `/etc/resolv.conf` contains Intel DNS servers (e.g.,
  `10.248.2.1`). This is typically inherited from the host network.
