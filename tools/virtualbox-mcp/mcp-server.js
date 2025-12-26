import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const vmTestScript = path.join(repoRoot, "scripts", "run_vm_test.sh");
const artifactRoot = path.join("/tmp", "ai-os-vm-tests");

function runCommand(command, args, options = {}) {
  return new Promise((resolve) => {
    const proc = spawn(command, args, {
      cwd: options.cwd ?? repoRoot,
      env: { ...process.env, ...(options.env ?? {}) },
    });

    let output = "";

    proc.stdout.on("data", (chunk) => {
      output += chunk.toString();
    });

    proc.stderr.on("data", (chunk) => {
      output += chunk.toString();
    });

    proc.on("close", (code) => {
      resolve({ code: code ?? 1, output });
    });
  });
}

function toolResult(result, header) {
  return {
    content: [
      {
        type: "text",
        text: `${header}\n\n${result.output || "(no output)"}`
      }
    ],
    isError: result.code !== 0
  };
}

function vmArtifactDir(vmName) {
  return path.join(artifactRoot, vmName);
}

function vmSerialLogPath(vmName) {
  return path.join(vmArtifactDir(vmName), "serial.log");
}

async function readTail(filePath, lineCount = 200) {
  const text = await fs.readFile(filePath, "utf8");
  const lines = text.split(/\r?\n/);
  return lines.slice(Math.max(0, lines.length - lineCount)).join("\n");
}

const server = new McpServer({
  name: "virtualbox",
  version: "1.0.0"
});

server.registerTool(
  "check_virtualbox_host",
  {
    title: "Check VirtualBox Host",
    description: "Verify VBoxManage can access the configured VirtualBox VM.",
    inputSchema: {
      vm_name: z.string().default("Aicustom")
    }
  },
  async ({ vm_name }) => {
    const result = await runCommand("VBoxManage", ["showvminfo", vm_name]);
    return toolResult(result, `VirtualBox host check for ${vm_name}`);
  }
);

server.registerTool(
  "show_vm_info",
  {
    title: "Show VM Info",
    description: "Show VirtualBox details for the configured VM.",
    inputSchema: {
      vm_name: z.string().default("Aicustom")
    }
  },
  async ({ vm_name }) => {
    const result = await runCommand("VBoxManage", ["showvminfo", vm_name]);
    return toolResult(result, `VirtualBox VM info for ${vm_name}`);
  }
);

server.registerTool(
  "start_vm_headless",
  {
    title: "Start VM Headless",
    description: "Start the configured VirtualBox VM in headless mode.",
    inputSchema: {
      vm_name: z.string().default("Aicustom")
    }
  },
  async ({ vm_name }) => {
    const result = await runCommand("VBoxManage", ["startvm", vm_name, "--type", "headless"]);
    return toolResult(result, `Headless VM start for ${vm_name}`);
  }
);

server.registerTool(
  "poweroff_vm",
  {
    title: "Power Off VM",
    description: "Power off the configured VirtualBox VM.",
    inputSchema: {
      vm_name: z.string().default("Aicustom")
    }
  },
  async ({ vm_name }) => {
    const result = await runCommand("VBoxManage", ["controlvm", vm_name, "poweroff"]);
    return toolResult(result, `Power off VM ${vm_name}`);
  }
);

server.registerTool(
  "attach_latest_iso",
  {
    title: "Attach Latest ISO",
    description: "Attach the newest ISO built in the repo output directory to the VirtualBox VM.",
    inputSchema: {
      vm_name: z.string().default("Aicustom")
    }
  },
  async ({ vm_name }) => {
    const result = await runCommand("bash", [
      "-lc",
      [
        `set -euo pipefail`,
        `ISO_PATH="$(ls -t "${path.join(repoRoot, "out")}"/*.iso | head -n1)"`,
        `VBoxManage storageattach "${vm_name}" --storagectl "IDE" --port 1 --device 0 --medium none || true`,
        `VBoxManage storageattach "${vm_name}" --storagectl "IDE" --port 1 --device 0 --type dvddrive --medium "${ISO_PATH}"`,
        `printf 'Attached ISO: %s\n' "${ISO_PATH}"`
      ].join("; ")
    ]);
    return toolResult(result, `Attach latest ISO to ${vm_name}`);
  }
);

server.registerTool(
  "tail_vm_serial_log",
  {
    title: "Tail VM Serial Log",
    description: "Read the tail of the serial log captured during a VirtualBox VM test run.",
    inputSchema: {
      vm_name: z.string().default("Aicustom"),
      lines: z.number().int().positive().max(1000).default(200)
    }
  },
  async ({ vm_name, lines }) => {
    const serialLog = vmSerialLogPath(vm_name);

    try {
      const tail = await readTail(serialLog, lines);
      return {
        content: [
          {
            type: "text",
            text: `Serial log tail for ${vm_name}\nPath: ${serialLog}\n\n${tail || "(empty log)"}`
          }
        ]
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Unable to read serial log for ${vm_name} at ${serialLog}\n\n${String(error)}`
          }
        ],
        isError: true
      };
    }
  }
);

server.registerTool(
  "run_virtualbox_test",
  {
    title: "Run VirtualBox ISO Test",
    description: "Build the Arch ISO from this repository, attach it to the Aicustom VM, boot it headless, and verify installer/model-install completion through serial console markers.",
    inputSchema: {
      vm_name: z.string().default("Aicustom"),
      boot_wait_seconds: z.number().int().positive().default(900)
    }
  },
  async ({ vm_name, boot_wait_seconds }) => {
    const result = await runCommand("bash", [vmTestScript], {
      cwd: repoRoot,
      env: {
        VM_NAME: vm_name,
        VM_BOOT_WAIT_SECONDS: String(boot_wait_seconds)
      }
    });

    return toolResult(result, `VirtualBox ISO install verification for ${vm_name}`);
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
