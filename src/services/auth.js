const USERS_KEY = 'amrin_demo_users'

const readUsers = () => {
  try {
    return JSON.parse(window.localStorage.getItem(USERS_KEY) || '[]')
  } catch {
    return []
  }
}
const writeUsers = (users) =>
  window.localStorage.setItem(USERS_KEY, JSON.stringify(users))

async function digest(value) {
  const bytes = new TextEncoder().encode(value)
  const buffer = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(buffer))
    .map((item) => item.toString(16).padStart(2, '0'))
    .join('')
}

export async function registerDemo({ name, email, password, city, role }) {
  if (import.meta.env.VITE_DEMO_AUTH !== 'true')
    throw new Error('Demo registration is disabled')
  if (role === 'admin' && !import.meta.env.VITE_ADMIN_INVITE)
    throw new Error('Operator invite required')
  const users = readUsers()
  if (users.some((user) => user.email === email))
    throw new Error('Account already exists')
  const salt = crypto.randomUUID()
  users.push({
    name,
    email,
    city,
    role,
    status: 'pending',
    salt,
    passwordHash: await digest(`${salt}:${password}`),
  })
  writeUsers(users)
  return { pending: true, name, email, city, role }
}

export async function loginDemo(email, password) {
  if (import.meta.env.VITE_DEMO_AUTH !== 'true')
    throw new Error('Demo authentication is disabled')
  const user = readUsers().find((item) => item.email === email)
  if (user) {
    if (user.status !== 'approved') {
      const error = new Error('Awaiting approval')
      error.code = 'PENDING_APPROVAL'
      throw error
    }
    if ((await digest(`${user.salt}:${password}`)) !== user.passwordHash)
      throw new Error('Invalid credentials')
    return {
      token: `demo-${user.email}`,
      role: user.role,
      name: user.name,
      city: user.city,
    }
  }
  const builtins = {
    admin: { password: 'admin', role: 'admin', name: 'Admin User' },
    worker: {
      password: 'worker',
      role: 'worker',
      name: 'Maintenance Worker',
      worker_id: 'worker-01',
    },
  }
  const builtin = builtins[email]
  if (!builtin || builtin.password !== password)
    throw new Error('Invalid credentials')
  return { token: `demo-${email}-token`, ...builtin }
}
