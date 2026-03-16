# n8n Workflows for BunkerWeb

This folder contains ready-to-use n8n workflows for BunkerWeb with **3 installation options** to suit all needs.

## 🚀 Quick Installation

### 🧩 AI Agent with Sub-workflows (Modular Architecture)

#### BunkerWeb AI Agent - MCP Integration.json

Conversational AI agent that uses **sub-workflows** for each tool.

✅ **Advantages**:
- Modular and reusable architecture
- Independently testable workflows
- Easier maintenance for large teams

❌ **Disadvantages**:
- 13 files to import
- More complex configuration
- Import order matters

**Prerequisites**:
- All sub-workflows imported first
- OpenAI credential configured
- MCP server accessible

**Installation**:

Manual import (in this order)
1. Import all MCP-Tool-*.json files
2. Import BunkerWeb-AI-Agent.json
3. Configure OpenAI
4. Activate the workflow


---

### 🛠️ MCP Sub-workflows (For modular architecture)

These workflows are used by `BunkerWeb-AI-Agent.json`.

| Sub-workflow | Description | Parameters |
|--------------|-------------|------------|
| **MCP-Tool-SearchDocs.json** | Search documentation | `query`, `limit`, `min_score` |
| **MCP-Tool-ListServices.json** | List services | `with_drafts` |
| **MCP-Tool-GetService.json** | Service details | `service`, `full` |
| **MCP-Tool-CreateService.json** | Create service | `server_name`, `is_draft`, `variables` |
| **MCP-Tool-UpdateService.json** | Update service | `service`, `server_name`, `is_draft`, `variables` |
| **MCP-Tool-DeleteService.json** | Delete service | `service` |
| **MCP-Tool-ListBans.json** | List banned IPs | None |
| **MCP-Tool-BanIP.json** | Ban IP(s) | `bans` (array) |
| **MCP-Tool-UnbanIP.json** | Unban IP(s) | `bans` (array) |
| **MCP-Tool-GlobalConfig.json** | Global config | `full`, `methods` |
| **MCP-Tool-ListInstances.json** | List instances | None |
| **MCP-Tool-ReloadConfig.json** | Reload config | `test` (boolean) |

---


### Configure Credentials

#### OpenAI Credential

1. In n8n: **Settings** → **Credentials** → **Add Credential**
2. Select **OpenAI API**
3. Add your OpenAI API key
4. Save

#### (Optional) Bearer Token for MCP

If your MCP server requires authentication:

1. Create a **Header Auth** credential
2. Header Name: `Authorization`
3. Value: `Bearer <your-token>`
4. Add this credential to HTTP Request nodes

### Step: Verify MCP Configuration

By default, workflows use `http://mcp:8080` to access the MCP server.

**If your configuration is different:**

```bash
# Check the MCP container name
docker ps | grep mcp

# Find the container IP
docker inspect <mcp-container-name> | grep IPAddress
```

**Modify the URL in workflows:**
- Open each workflow
- In **HTTP Request** nodes, modify the URL
- Possible options:
  - `http://<container-name>:8080`
  - `http://<container-ip>:8080`
  - `http://host.docker.internal:8080` (if n8n on host)

---

## 💬 Usage Examples

### With BunkerWeb-Complete-Agent

#### Documentation Search

```
You: How do I configure ModSecurity with BunkerWeb?

Agent: I'll search the documentation...
[Uses search_bunkerweb_docs]

Here's how to configure ModSecurity:

1. **Basic activation**
   To enable ModSecurity, set:
   - USE_MODSECURITY=yes
   - USE_MODSECURITY_CRS=yes (for OWASP Core Rule Set)

2. **Anomaly scoring mode** (recommended)
   - MODSECURITY_CRS_ACTION=score
   - More flexible, fewer false positives

📖 Full documentation: https://docs.bunkerweb.io/...
```

#### Service Management

```
You: List all my BunkerWeb services

Agent: I'm checking your services...
[Uses list_services]

Configured BunkerWeb services (3):

1. **example.com** - ✅ Online
   • ModSecurity: yes
   • Antibot: javascript

2. **test.local** - 📝 Draft

3. **api.example.com** - ✅ Online
   • ModSecurity: yes
```

#### Service Creation

```
You: Create a new service for "mysite.com" with ModSecurity and antibot enabled

Agent: I'm creating the "mysite.com" service with security settings...
[Uses create_service]

✅ Service **mysite.com** created successfully.

**Applied configuration:**
• USE_MODSECURITY: yes
• USE_ANTIBOT: javascript

⚠️ Don't forget to reload the configuration with `reload_config`.

Would you like me to reload now?
```

#### Ban Management

```
You: Ban IP 192.168.1.100 for 1 hour due to brute force attempt

Agent: I'm banning IP 192.168.1.100 for 1 hour...
[Uses ban_ip]

✅ 1 IP banned successfully:

1. **192.168.1.100**
   • Reason: Brute force attempt
   • Duration: 1h 0m
   • Scope: Global

The IP is now blocked on all your services.
```

---


### Modifying MCP URLs

If your MCP server is elsewhere than `http://mcp:8080`, modify in **each HTTP Request node**:

```json
"url": "http://YOUR-MCP-URL:8080/mcp/v1/tools/TOOL_NAME/call"
```

---

### The AI agent is not responding

**1. Check the OpenAI credential:**
- Settings → Credentials → OpenAI API
- Test the API key at https://platform.openai.com

**2. Check OpenAI credits:**
- Log in to platform.openai.com
- Check your balance

**3. Check n8n execution logs:**
- Open the workflow
- Click on "Executions" to see the history

### Tools are not returning results

**1. Test the MCP endpoint directly:**
```bash
curl -X POST http://mcp:8080/mcp/v1/tools/list_services/call \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"with_drafts": true}}'
```

**2. Check MCP server logs:**
```bash
docker logs mcp-bunkerweb --tail=100 -f
```

**3. Check BunkerWeb configuration:**
```bash
# Verify that the BunkerWeb API is accessible
curl http://bw-api:8888/health
```

### "Workflow not found" error for sub-workflows

This happens when `BunkerWeb-AI-Agent.json` is imported before the sub-workflows.

**Solution:**
1. Delete `BunkerWeb-AI-Agent.json`
2. Import ALL `MCP-Tool-*.json` files first
3. Then import `BunkerWeb-AI-Agent.json`

**Alternative (simpler):**
- Use `BunkerWeb-Complete-Agent.json` instead
- No sub-workflows needed!

---

**Enjoy using BunkerWeb! 🚀**
