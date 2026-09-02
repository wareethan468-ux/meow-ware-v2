import { Icon } from '../Icons';

export function Brand({ tagline=false }) {
  return <span className="brand"><img src="/meow-ware-icon.png" alt=""/><span><b>Meow Ware</b><small>{tagline?'FastFlags made easy.':'v1.3'}</small></span></span>;
}

export function SiteHeader({ open, onToggle }) {
  return <header className="top"><a href="#top"><Brand/></a><button className="mobile" onClick={onToggle} aria-label="Toggle navigation"><Icon name={open?'minus':'menu'}/></button><nav className={open?'open':''}><a href="#product">Product</a><a href="#features">Features</a><a href="#new">What’s new</a><a href="#faq">FAQ</a></nav><a className="download" href="./Meow-Ware-v1.3.exe" download>Download <Icon name="download" size={13}/></a></header>;
}

export function SiteFooter() {
  return <footer className="site-foot"><Brand tagline/><nav><a href="#product">Product</a><a href="#features">Features</a><a href="#faq">FAQ</a></nav><small>© 2026 Meow Ware</small></footer>;
}

export function SectionIntro({ tag, title, text }) {
  return <header className="intro"><small>{tag}</small><div><h2>{title}</h2>{text&&<p>{text}</p>}</div></header>;
}
