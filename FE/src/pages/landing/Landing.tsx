import Header from './components/Header'
import Hero from './components/Hero'
import Showcase from './components/Showcase'
import Modes from './components/Modes'
import Cta from './components/Cta'
import './landing.css'

export default function Landing() {
  return (
    <>
      <Header />
      <Hero />
      <Modes />
      <Showcase />
      <Cta />
    </>
  )
}
