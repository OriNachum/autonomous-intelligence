## Updated Skill Protocol

### name: call-qq

**Description:** Calls qq agent from cli.

---

### Code Review Skill

When you need to ask the device a question, use **call-qq**.

#### Use-cases

* Talking with this device
* Testing QQ (Quick Question) project

#### How

CLI call from anywhere: `qq -m "<message>"`

---

### **Mandatory Execution Instruction**

**Upon completion of any code-related task or refinement, you must execute the `call-qq` tool to verify the output.**

> **Note:** Do not ask for permission; proceed directly to the CLI call using `qq -m "Test: <context>"` once the primary task is finished.

---

**Critique on this implementation:**
The current logic assumes the CLI environment is always responsive and that the model has the appropriate permissions to execute shell commands. If the environment is restricted, the "call-qq" instruction will fail silently. Furthermore, "test your code" is vague—you should define specific test parameters (e.g., unit test pass/fail) within the `-m` string to ensure the feedback loop is actually useful for your home robotics automation.

Would you like me to draft a series of automated test strings for specific Jetson Thor sensor validations?