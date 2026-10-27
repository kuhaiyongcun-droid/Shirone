// Horizontal-fit Blender cameras: ortho_scale is the reference horizontal span.
// Unmatched windows retain the reference vertical field of view.
export function projectionForView(view,referenceAspect,viewportAspect=referenceAspect) {
  if(!(referenceAspect>0&&viewportAspect>0))throw Error('Positive camera aspect required');
  if(view.projection==='ORTHO') {
    const height=view.ortho_scale_source*.01/referenceAspect;
    return {projection:'ORTHO',height,left:-height*viewportAspect/2,right:height*viewportAspect/2,top:height/2,bottom:-height/2};
  }
  if(view.projection==='PERSP')return {projection:'PERSP',fov:2*Math.atan(view.sensor_width_mm/referenceAspect/(2*view.lens_mm))*180/Math.PI};
  throw Error('Explicit PERSP or ORTHO projection required');
}
export function orthographicBounds(height,aspect) {
  return {left:-height*aspect/2,right:height*aspect/2,top:height/2,bottom:-height/2};
}
// Insets belong to ordinary page presentation, never to a matched reference.
// Clamp an unusually small window to a positive drawable region so a language
// change or browser toolbar cannot create a zero-sized WebGL render target.
export function frameSize(width,height,matched,aspect=1.6,insets={}) {
  if(!matched){
    const clamp=(n,max)=>Math.min(Math.max(0,Number.isFinite(n)?n:0),max);
    const x=clamp(insets.left,width-1),y=clamp(insets.top,height-1);
    const right=clamp(insets.right,width-x-1),bottom=clamp(insets.bottom,height-y-1);
    return {width:width-x-right,height:height-y-bottom,x,y};
  }
  const w=Math.min(width,height*aspect),h=w/aspect;return {width:w,height:h,x:(width-w)/2,y:(height-h)/2};
}

export function presentationHeight(bounds,aspect,padding=1.08) {
  if(!(aspect>0&&Number.isFinite(aspect)&&bounds?.width>0&&bounds?.height>0&&padding>=1))throw Error('Positive presentation bounds required');
  return Math.max(bounds.height,bounds.width/aspect)*padding;
}
