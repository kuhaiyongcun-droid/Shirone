// Measure the ordinary mobile drawing area after translated controls are laid
// out. Reference captures always retain the original full-page frame.
export function presentationInsets(viewport,matched=false) {
  const box=viewport.getBoundingClientRect(),experience=document.getElementById('experience');
  let top=0,bottom=0;
  if(!matched&&(innerWidth<=650||innerHeight<=500)){
    const header=document.querySelector('.masthead').getBoundingClientRect();
    const footer=document.querySelector('.footer').getBoundingClientRect();
    top=Math.max(0,Math.ceil(header.bottom-box.top+16));
    bottom=Math.max(0,Math.ceil(box.bottom-footer.top+16));
  }
  experience.style.setProperty('--presentation-top',top+'px');
  experience.style.setProperty('--presentation-bottom',bottom+'px');
  return {top,bottom,left:0,right:0};
}
