import { useState } from 'react';
import { Icon } from './Icons';
import ProductDemo from './components/ProductDemo';
import { DownloadPanel, FAQSection, FeatureSection, Metrics, UpdateSection } from './components/MarketingSections';
import { SectionIntro, SiteFooter, SiteHeader } from './components/SiteChrome';

export default function App() {
  const [mobileOpen,setMobileOpen]=useState(false);
  return <div id="top">
    <SiteHeader open={mobileOpen} onToggle={()=>setMobileOpen(!mobileOpen)}/>
    <main>
      <section className="hero"><div><p><i/> Version 1.3 for Windows</p><h1>FastFlags,<br/>made manageable.</h1><h2>A precise desktop workspace for finding, organizing, theming, and applying Roblox FastFlags.</h2><aside><a className="cta" href="./Meow-Ware-v1.3.exe" download>Download for Windows <Icon name="download" size={13}/></a><a href="#product">Try the demo</a></aside><footer><span><Icon name="check"/>Standalone</span><span><Icon name="check"/>Local settings</span><span><Icon name="check"/>Windows 10/11</span></footer></div><ol><li>Editor</li><li>Offsets</li><li>Themes</li></ol></section>
      <section id="product" className="section demo-wrap"><SectionIntro tag="PRODUCT DEMO" title="One workspace. Every control." text="Use the icon menu to explore the product."/><ProductDemo/></section>
      <Metrics/><FeatureSection/><UpdateSection/><FAQSection/><DownloadPanel/>
    </main>
    <SiteFooter/>
  </div>;
}
