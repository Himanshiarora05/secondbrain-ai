export function AuroraBackground() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden -z-10 select-none"
    >
      {/* 
        Atmospheric Navy/Blue Hero Glow 
        Layer 1: Primary upper/central deep-blue ambient glow behind the hero
        Layer 2: Subtle secondary lower-center soft wash
        Layer 3: Seamless dark vignette fading corners into #05070C
      */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(ellipse 950px 580px at 50% 26%, rgba(28, 68, 162, 0.38) 0%, rgba(18, 46, 120, 0.24) 35%, rgba(10, 26, 75, 0.10) 62%, transparent 82%),
            radial-gradient(ellipse 750px 420px at 50% 64%, rgba(16, 42, 110, 0.15) 0%, rgba(10, 24, 70, 0.06) 45%, transparent 75%)
          `,
        }}
      />

      {/* Very soft, broad atmospheric diffusion layer */}
      <div
        className="absolute top-[8%] left-1/2 -translate-x-1/2 w-[800px] h-[460px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, rgba(32, 78, 185, 0.22) 0%, rgba(18, 48, 125, 0.12) 45%, transparent 70%)',
          filter: 'blur(70px)',
          WebkitFilter: 'blur(70px)',
        }}
      />

      {/* Subtle vignette: Keeps center clear while softening edges and corners into #05070C */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at 50% 35%, transparent 45%, rgba(5, 7, 12, 0.40) 75%, #05070C 100%)',
        }}
      />
    </div>
  )
}
