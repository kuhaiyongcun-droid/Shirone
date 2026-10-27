// Offline object model for testing actual recipe initialization; no renderer or Three implementation is claimed.
export const LinearSRGBColorSpace='test-linear';
class Vector {fromArray(value){this.value=[...value];return this;}}
export class Group {
  constructor(){this.children=[];this.visible=true;}
  add(...items){this.children.push(...items);}
  remove(item){this.children=this.children.filter(child=>child!==item);}
}
export class Color {setRGB(...value){this.value=value;return this;}}
class Light {
  constructor(color,intensity){
    this.isLight=true;this.visible=true;this.color=color;this.intensity=intensity;this.position=new Vector();
    this.target={position:new Vector()};this.shadow={mapSize:{set(){}},camera:{updateProjectionMatrix(){}},dispose(){}};
  }
}
export class DirectionalLight extends Light {}
export class SpotLight extends Light {}
