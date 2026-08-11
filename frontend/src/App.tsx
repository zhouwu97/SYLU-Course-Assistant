// 5 个主页面（计划 §34）：dashboard / courses / plan / automation / settings
import { NavLink, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Courses from "./pages/Courses";
import Plan from "./pages/Plan";
import Automation from "./pages/Automation";
import Settings from "./pages/Settings";

const NAV = [
  { to: "/", label: "总览", end: true },
  { to: "/courses", label: "找课程" },
  { to: "/plan", label: "选课计划" },
  { to: "/automation", label: "自动候补" },
  { to: "/settings", label: "设置" },
];

export default function App() {
  return (
    <div className="layout">
      <header className="topbar">
        <div className="brand">SYLU Course Assistant</div>
        <nav>
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/courses" element={<Courses />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/automation" element={<Automation />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
